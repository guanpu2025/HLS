"""Host-side check that the generated kernel matches a local reference.

The official ``*_tb.cpp`` is never opened. The reference source is compiled
beside the solution and is not returned to the model; a mismatch report only
contains values. Tasks without a reference are skipped. ``hls_stream`` is
skipped. ``ap_fixed`` is compiled with the Vitis headers when ``v++`` is on
``PATH``. A host compile that fails in the driver, not in the solution, is
also skipped rather than failed.

Fill values follow the official polybench-style ranges so the reference can
finish: ``ap_fixed``/float in ``[0, 1)``, ``alpha``/``beta`` 1.5/1.2,
``float_n`` the leading array extent, ``char`` in ``0..3``. 32/64-bit integers
use IEEE bit patterns (0, 1, Inf, NaN, sign bit) so soft-float compares see
unordered cases. A 2-D integer ``table`` next to a ``char`` sequence is zeroed,
like the official nussinov testbench. Square real matrices get a diagonal boost
so ``sqrt`` kernels stay defined. Structs are ``memset``/``memcmp``, not
constructed from ``double``. A host compile failure is skipped; it is not a
functional mismatch. The check still compares against the local reference,
never ``tb_data.txt``.

Enable it in the agent with ``AGENT_SELF_CHECK=1``. The default is off.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass


_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.S)
_COMMENT_LINE = re.compile(r"//.*?$", re.M)
_TYPEDEF_ARRAY = re.compile(
    r"typedef\s+(.+?)\s+([A-Za-z_]\w*)\s*((?:\s*\[[^\]]+\])+)\s*;",
    re.S,
)
_HLS_ONLY = re.compile(r"hls_stream")


@dataclass
class Arg:
    base_type: str
    name: str
    dims: list[str]
    pointer: bool
    const: bool
    typedef_name: str = ""


def self_check(
    task_dir: str,
    source: str,
    top: str,
    interface: str,
    headers: dict[str, str],
    timeout_s: float = 30.0,
) -> tuple[int, str]:
    """Return ``(rc, log)``.

    ``0`` match, ``1`` mismatch or the solution failed to compile, ``-1`` skipped.
    """
    if timeout_s <= 1:
        return -1, "self-check skipped: no time left"
    if _HLS_ONLY.search(interface or ""):
        return -1, "self-check skipped: host compiler cannot build hls_stream"
    ref = _reference_path(task_dir)
    if ref is None:
        return -1, "self-check skipped: no local reference"
    parsed = parse_signature(interface, top)
    if parsed is None:
        return -1, f"self-check skipped: could not parse prototype of {top}"
    ret, args = parsed
    if any(a.name == "" for a in args):
        return -1, "self-check skipped: unnamed parameter"

    work = tempfile.mkdtemp(prefix="selfcheck_")
    try:
        for name, text in headers.items():
            with open(os.path.join(work, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        with open(os.path.join(work, "dut.cpp"), "w", encoding="utf-8") as fh:
            fh.write(source)
        shutil.copy(ref, os.path.join(work, "ref.cpp"))
        driver = _driver(top, ret, args, headers)
        with open(os.path.join(work, "check.cpp"), "w", encoding="utf-8") as fh:
            fh.write(driver)
        binary = os.path.join(work, "check")
        cmd = ["g++", "-std=c++17", "-O1", "-I", work, "-I", task_dir]
        inc = _vitis_include()
        if inc:
            cmd.extend(["-I", inc])
        cmd.extend(["-o", binary, os.path.join(work, "check.cpp")])
        compile_log = _run(
            cmd,
            timeout_s=min(timeout_s, 60.0),
            cwd=work,
        )
        if compile_log[0] != 0:
            text = compile_log[1]
            return -1, "self-check skipped: host compile failed\n" + text[-800:]
        run_rc, run_log = _run([binary], timeout_s=min(timeout_s, 30.0), cwd=task_dir)
        if run_rc == 0:
            return 0, "self-check passed"
        if run_rc == _RUN_TIMEOUT or "SELF_CHECK_REF_OK" not in run_log:
            return -1, "self-check skipped: reference crashed or the run timed out\n" + _visible_log(run_log)[-800:]
        if run_rc < 0:
            return 1, _solution_crash(run_rc, run_log)
        return 1, "self-check failed\n" + _visible_log(run_log)[-1500:]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _visible_log(log: str) -> str:
    """Drop the reference-finished marker. It is only for crash classification."""
    lines = [ln for ln in log.splitlines() if ln.strip() != "SELF_CHECK_REF_OK"]
    return "\n".join(lines)


def _solution_crash(rc: int, log: str) -> str:
    """The reference finished and the solution then died on a signal."""
    if rc == -11:
        why = "段错误。检查数组下标是否越界。"
    elif rc == -8:
        why = "浮点异常。"
    else:
        why = f"信号 {-rc}。"
    return (
        "self-check failed: solution crashed after the reference accepted this input\n"
        + why + "\n" + _visible_log(log)[-800:]
    )


def _vitis_include() -> str | None:
    """Directory that contains ``ap_fixed.h``, if this machine has Vitis."""
    env = os.environ.get("HLS_INCLUDE", "").strip()
    if env and os.path.isfile(os.path.join(env, "ap_fixed.h")):
        return env
    vpp = shutil.which("v++")
    if not vpp:
        return None
    inc = os.path.abspath(os.path.join(os.path.dirname(vpp), os.pardir, "include"))
    if os.path.isfile(os.path.join(inc, "ap_fixed.h")):
        return inc
    return None


def parse_signature(interface: str, top: str) -> tuple[str, list[Arg]] | None:
    text = _strip_comments(interface or "")
    typedefs = _typedef_arrays(text)
    match = re.search(rf"\b{re.escape(top)}\s*\(", text)
    if not match:
        return None
    args_src, end = _take_balanced(text, match.end() - 1)
    if args_src is None:
        return None
    tail = text[end:end + 80]
    if not re.match(r"\s*;", tail):
        return None
    ret = _return_type(text, match.start(), top)
    if not ret:
        return None
    args: list[Arg] = []
    for raw in _split_args(args_src):
        arg = _parse_arg(raw, typedefs)
        if arg is None:
            return None
        args.append(arg)
    return ret, args


def _reference_path(task_dir: str) -> str | None:
    meta = os.path.join(task_dir, "task.json")
    if not os.path.isfile(meta):
        return None
    try:
        with open(meta, encoding="utf-8") as fh:
            ref = json.load(fh).get("reference") or ""
    except (OSError, json.JSONDecodeError):
        return None
    if not ref or os.path.basename(ref).endswith("_tb.cpp"):
        return None
    path = ref if os.path.isabs(ref) else os.path.join(task_dir, ref)
    if not os.path.isfile(path):
        return None
    return path


def _return_type(text: str, name_at: int, top: str) -> str:
    """Type tokens on the line immediately before the function name."""
    prefix = text[:name_at]
    lines = prefix.splitlines() or [prefix]
    collected: list[str] = []
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            break
        if not stripped:
            if collected:
                break
            continue
        collected.append(stripped)
        break
    ret = " ".join(reversed(collected))
    ret = re.sub(rf"\b{re.escape(top)}\s*$", "", ret).strip()
    return " ".join(ret.split())


def _strip_comments(text: str) -> str:
    text = _COMMENT_BLOCK.sub(" ", text)
    return _COMMENT_LINE.sub(" ", text)


def _typedef_arrays(text: str) -> dict[str, tuple[str, list[str]]]:
    found: dict[str, tuple[str, list[str]]] = {}
    for match in _TYPEDEF_ARRAY.finditer(text):
        base = " ".join(match.group(1).split())
        dims = re.findall(r"\[([^\]]+)\]", match.group(3))
        found[match.group(2)] = (base, [d.strip() for d in dims])
    return found


def _take_balanced(text: str, open_at: int) -> tuple[str | None, int]:
    if open_at >= len(text) or text[open_at] != "(":
        return None, open_at
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_at + 1:i], i + 1
    return None, open_at


def _split_args(src: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in src:
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p and p != "void"]


def _parse_arg(raw: str, typedefs: dict[str, tuple[str, list[str]]]) -> Arg | None:
    dims = [d.strip() for d in re.findall(r"\[([^\]]+)\]", raw)]
    core = re.sub(r"\s*\[[^\]]+\]", "", raw).strip()
    pointer = "*" in core
    core = core.replace("*", " ")
    tokens = core.split()
    if not tokens:
        return None
    name = tokens[-1]
    if not re.match(r"[A-Za-z_]\w*$", name):
        return None
    type_tokens = tokens[:-1]
    const = "const" in type_tokens
    base_tokens = [t for t in type_tokens if t != "const"]
    if not base_tokens:
        return None
    base = " ".join(base_tokens)
    typedef_name = ""
    if base in typedefs and not dims:
        typedef_name = base
        base, dims = typedefs[base]
    if re.search(r"\b(struct|union|enum)\b", base) and not dims:
        return None
    return Arg(base_type=base, name=name, dims=dims, pointer=pointer,
               const=const, typedef_name=typedef_name)


def _driver(top: str, ret: str, args: list[Arg], headers: dict[str, str]) -> str:
    header_includes = "\n".join(f'#include "{name}"' for name in headers)
    lines = [
        "#include <cmath>",
        "#include <cstdint>",
        "#include <cstdio>",
        "#include <cstdlib>",
        "#include <cstring>",
        header_includes,
        "namespace refns {",
        f"#define {top} {top}_ref",
        '#include "ref.cpp"',
        f"#undef {top}",
        "}",
        "namespace dutns {",
        f"#define {top} {top}_dut",
        '#include "dut.cpp"',
        f"#undef {top}",
        "}",
        "static uint32_t lcg_state;",
        "static uint32_t lcg() { lcg_state = lcg_state * 1664525u + 1013904223u; return lcg_state; }",
        "static int pat_i;",
        "static const uint64_t kPat64[8] = {",
        "    0ull, 1ull, ~0ull, 1ull << 63,",
        "    0x7ff8000000000000ull, 0x7ff0000000000001ull,",
        "    0x7ff0000000000000ull, 0xfff0000000000000ull};",
        "static const uint32_t kPat32[8] = {",
        "    0u, 1u, 0xffffffffu, 0x80000000u,",
        "    0x7fc00000u, 0x7f800001u, 0x7f800000u, 0xff800000u};",
        "template <typename T, typename = void>",
        "struct has_to_double : std::false_type {};",
        "template <typename T>",
        "struct has_to_double<T, std::void_t<decltype(std::declval<const T&>().to_double())>> : std::true_type {};",
        "template <typename T>",
        "static void fill_one(T& slot) {",
        "    if constexpr (std::is_floating_point<T>::value || has_to_double<T>::value) {",
        "        slot = static_cast<T>((lcg() % 1000) / 1000.0);",
        "    } else if constexpr (std::is_integral<T>::value && sizeof(T) == 1) {",
        "        slot = static_cast<T>(lcg() % 4);",
        "    } else if constexpr (std::is_integral<T>::value && sizeof(T) == 8) {",
        "        uint64_t bits = kPat64[pat_i % 8];",
        "        pat_i++;",
        "        std::memcpy(&slot, &bits, sizeof(bits));",
        "    } else if constexpr (std::is_integral<T>::value && sizeof(T) == 4) {",
        "        uint32_t bits = kPat32[pat_i % 8];",
        "        pat_i++;",
        "        std::memcpy(&slot, &bits, sizeof(bits));",
        "    } else if constexpr (std::is_integral<T>::value) {",
        "        slot = static_cast<T>(lcg() % 16);",
        "    } else {",
        "        std::memset(&slot, 0, sizeof(slot));",
        "    }",
        "}",
        "template <typename T>",
        "static void add_diag(T& slot, int n) {",
        "    if constexpr (std::is_floating_point<T>::value || has_to_double<T>::value) {",
        "        slot = slot + static_cast<T>(n);",
        "    } else {",
        "        (void)slot;",
        "        (void)n;",
        "    }",
        "}",
        "template <typename T>",
        "static void show_val(const T& v) {",
        "    if constexpr (std::is_floating_point<T>::value) {",
        "        std::printf(\"%g\", static_cast<double>(v));",
        "    } else if constexpr (has_to_double<T>::value) {",
        "        std::printf(\"%g\", v.to_double());",
        "    } else if constexpr (std::is_integral<T>::value) {",
        "        using U = std::make_unsigned_t<T>;",
        "        std::printf(\"0x%llx\", static_cast<unsigned long long>(static_cast<U>(v)));",
        "    } else {",
        "        std::printf(\"?\");",
        "    }",
        "}",
        "template <typename T>",
        "static bool same(const T& a, const T& b) {",
        "    if constexpr (std::is_floating_point<T>::value) {",
        "        double d = std::fabs(static_cast<double>(a) - static_cast<double>(b));",
        "        double s = std::fabs(static_cast<double>(a)) + std::fabs(static_cast<double>(b));",
        "        return d <= 1e-4 || d <= 1e-3 * s;",
        "    } else if constexpr (has_to_double<T>::value) {",
        "        double av = a.to_double();",
        "        double bv = b.to_double();",
        "        if (std::isnan(av) && std::isnan(bv)) return true;",
        "        double d = std::fabs(av - bv);",
        "        double s = std::fabs(av) + std::fabs(bv);",
        "        return d <= 1e-4 || d <= 1e-3 * s;",
        "    } else if constexpr (std::is_integral<T>::value) {",
        "        return a == b;",
        "    } else {",
        "        return std::memcmp(&a, &b, sizeof(T)) == 0;",
        "    }",
        "}",
    ]
    # std::is_floating_point needs <type_traits>
    lines.insert(5, "#include <type_traits>")

    def slots(arg: Arg) -> int:
        # Some kernels index a typedef pointer as ptr[i], stepping by the
        # whole array. Extra copies keep those reads inside the buffer.
        return 20 if arg.pointer and arg.typedef_name else 1

    def index_dims(arg: Arg) -> list[str]:
        if slots(arg) > 1:
            return ["20"] + arg.dims
        return arg.dims

    def decl(arg: Arg, suffix: str) -> str:
        if arg.typedef_name and arg.pointer:
            extra = "[20]" if slots(arg) > 1 else ""
            return f"{arg.typedef_name} {arg.name}_{suffix}{extra};"
        dims = "".join(f"[{d}]" for d in arg.dims)
        return f"{arg.base_type} {arg.name}_{suffix}{dims};"

    def leading_extent() -> str:
        named = {"data", "a", "a_in", "input"}
        for arg in args:
            if arg.dims and arg.name.lower() in named:
                return f"({arg.dims[0]})"
        for arg in args:
            if len(arg.dims) >= 2:
                return f"({arg.dims[0]})"
        for arg in args:
            if arg.dims:
                return f"({arg.dims[0]})"
        return "(16)"

    def fill_scalar(arg: Arg, suffix: str) -> str:
        target = f"{arg.name}_{suffix}"
        name = arg.name.lower()
        if name == "alpha":
            return f"{target} = static_cast<{arg.base_type}>(1.5);"
        if name == "beta":
            return f"{target} = static_cast<{arg.base_type}>(1.2);"
        if name in ("float_n", "n", "fn"):
            return f"{target} = static_cast<{arg.base_type}>({leading_extent()});"
        return f"fill_one({target});"

    def _has_char_seq() -> bool:
        return any(
            len(a.dims) == 1 and "char" in a.base_type.lower()
            for a in args
        )

    def fill_stmt(arg: Arg, suffix: str) -> str:
        target = f"{arg.name}_{suffix}"
        dims = index_dims(arg)
        if dims:
            idx = [f"i{n}" for n in range(len(dims))]
            loops = " ".join(
                f"for (int {idx[n]} = 0; {idx[n]} < ({dim}); ++{idx[n]})"
                for n, dim in enumerate(dims)
            )
            sub = "".join(f"[{i}]" for i in idx)
            name = arg.name.lower()
            zero_table = (
                len(dims) == 2
                and "int" in arg.base_type.lower()
                and (
                    name in ("table", "dp")
                    or _has_char_seq()
                )
            )
            if zero_table:
                return (
                    f"{loops} {target}{sub} = "
                    f"static_cast<{arg.base_type}>(0);"
                )
            return f"{loops} fill_one({target}{sub});"
        return fill_scalar(arg, suffix)

    def boost_diag(arg: Arg, suffix: str) -> str | None:
        dims = index_dims(arg)
        if len(dims) != 2 or dims[0].strip() != dims[1].strip():
            return None
        target = f"{arg.name}_{suffix}"
        dim = dims[0]
        return (
            f"for (int d = 0; d < ({dim}); ++d) "
            f"add_diag({target}[d][d], static_cast<int>({dim}));"
        )

    def pass_expr(arg: Arg, suffix: str) -> str:
        if slots(arg) > 1:
            return f"&{arg.name}_{suffix}[0]"
        if arg.pointer:
            return f"&{arg.name}_{suffix}"
        return f"{arg.name}_{suffix}"

    blob = "\n".join(headers.values())
    fixed = "ap_fixed" in blob or "ap_int" in blob or "ap_ufixed" in blob
    trials = 2 if fixed else 8
    body = ["int main() {", f"    int trials = {trials};", "    for (int trial = 0; trial < trials; ++trial) {",
            "        lcg_state = 0x12345678u + static_cast<uint32_t>(trial) * 97u;",
            "        pat_i = trial;"]
    for arg in args:
        if arg.const or not arg.dims and not arg.pointer:
            body.append("        " + decl(arg, "in"))
            body.append("        " + fill_stmt(arg, "in"))
            boost = boost_diag(arg, "in")
            if boost:
                body.append("        " + boost)
        else:
            body.append("        " + decl(arg, "dut"))
            body.append("        " + decl(arg, "ref"))
            body.append("        " + decl(arg, "in"))
            body.append("        " + fill_stmt(arg, "dut"))
            boost = boost_diag(arg, "dut")
            if boost:
                body.append("        " + boost)
            body.append(f"        std::memcpy(&{arg.name}_ref, &{arg.name}_dut, sizeof({arg.name}_dut));")
            body.append(f"        std::memcpy(&{arg.name}_in, &{arg.name}_dut, sizeof({arg.name}_dut));")

    def dump_values(indent: str, dut_expr: str, ref_expr: str, failing: Arg | None, sub: str, label: str) -> list[str]:
        """One failure report: inputs, then `name dut=... ref=...`."""
        lines_out = [f'{indent}std::printf("inputs");']
        for arg in args:
            if arg.const or (not arg.dims and not arg.pointer):
                lines_out.append(
                    f'{indent}std::printf(" {arg.name}="); show_val({arg.name}_in);'
                )
            elif (
                failing is not None and sub and arg.dims
                and index_dims(arg) == index_dims(failing)
            ):
                # In-place arrays: the snapshot is the real input. Pointer
                # outputs such as z0Ptr are only written, so their pre-filled
                # bytes are not inputs and must not be printed.
                lines_out.append(
                    f'{indent}std::printf(" {arg.name}{sub}="); show_val({arg.name}_in{sub});'
                )
            elif (
                failing is not None
                and sub
                and len(index_dims(arg)) == 1
                and failing.dims
                and len(index_dims(failing)) == 2
            ):
                # seq[i], seq[j] next to table[i][j]
                lines_out.append(
                    f'{indent}std::printf(" {arg.name}[i0]="); show_val({arg.name}_in[i0]);'
                )
                lines_out.append(
                    f'{indent}std::printf(" {arg.name}[i1]="); show_val({arg.name}_in[i1]);'
                )
        lines_out.append(f'{indent}std::printf("\\n");')
        lines_out.append(f'{indent}std::printf("{label} dut="); show_val({dut_expr});')
        lines_out.append(f'{indent}std::printf(" ref="); show_val({ref_expr});')
        lines_out.append(f'{indent}std::printf("\\n");')
        return lines_out

    dut_args = []
    ref_args = []
    for arg in args:
        if arg.const or not arg.dims and not arg.pointer:
            dut_args.append(pass_expr(arg, "in"))
            ref_args.append(pass_expr(arg, "in"))
        else:
            dut_args.append(pass_expr(arg, "dut"))
            ref_args.append(pass_expr(arg, "ref"))
    call_dut = f"dutns::{top}_dut({', '.join(dut_args)})"
    call_ref = f"refns::{top}_ref({', '.join(ref_args)})"
    if ret == "void":
        body.append(f"        {call_ref};")
        body.append('        std::printf("SELF_CHECK_REF_OK\\n");')
        body.append("        std::fflush(stdout);")
        body.append(f"        {call_dut};")
    else:
        body.append(f"        auto ref_ret = {call_ref};")
        body.append('        std::printf("SELF_CHECK_REF_OK\\n");')
        body.append("        std::fflush(stdout);")
        body.append(f"        auto dut_ret = {call_dut};")
        body.append("        if (!same(dut_ret, ref_ret)) {")
        body.append('            std::printf("self-check failed: return value mismatch\\n");')
        body.extend(dump_values("            ", "dut_ret", "ref_ret", None, "", "返回值"))
        body.append("            return 1;")
        body.append("        }")

    for arg in args:
        if arg.const or (not arg.dims and not arg.pointer):
            continue
        if not arg.dims:
            body.append(f"        if (!same({arg.name}_dut, {arg.name}_ref)) {{")
            body.append(
                f'            std::printf("self-check failed: {arg.name} mismatch\\n");'
            )
            body.extend(dump_values(
                "            ", f"{arg.name}_dut", f"{arg.name}_ref", arg, "", arg.name,
            ))
            body.append("            return 1;")
            body.append("        }")
            continue
        dims = index_dims(arg)
        idx = [f"i{n}" for n in range(len(dims))]
        loops = []
        close = []
        for n, dim in enumerate(dims):
            loops.append(f"for (int {idx[n]} = 0; {idx[n]} < ({dim}); ++{idx[n]}) {{")
            close.append("}")
        sub = "".join(f"[{i}]" for i in idx)
        body.append("        " + " ".join(loops))
        body.append(
            f"            if (!same({arg.name}_dut{sub}, {arg.name}_ref{sub})) {{"
        )
        body.append(
            f'                std::printf("self-check failed: {arg.name}{sub} mismatch\\n");'
        )
        body.extend(dump_values(
            "                ", f"{arg.name}_dut{sub}", f"{arg.name}_ref{sub}", arg, sub,
            f"{arg.name}{sub}",
        ))
        body.append("                return 1;")
        body.append("            }")
        body.append("        " + " ".join(close))
    body.append("    }")
    body.append("    return 0;")
    body.append("}")
    return "\n".join(lines + body) + "\n"


_RUN_TIMEOUT = -1000


def _run(cmd: list[str], timeout_s: float, cwd: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            timeout=timeout_s, errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") + (exc.stderr or "")
        return _RUN_TIMEOUT, out
    except OSError as exc:
        return _RUN_TIMEOUT, str(exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="compare a solution with the local reference")
    ap.add_argument("--task", required=True)
    ap.add_argument("--solution", required=True)
    ap.add_argument("--top", default="")
    args = ap.parse_args(argv)
    from .main import infer_top, split_interface

    with open(os.path.join(args.task, "interface.txt"), encoding="utf-8") as fh:
        interface = fh.read()
    prompt_path = os.path.join(args.task, "prompt.txt")
    prompt = ""
    if os.path.isfile(prompt_path):
        with open(prompt_path, encoding="utf-8") as fh:
            prompt = fh.read()
    with open(args.solution, encoding="utf-8") as fh:
        source = fh.read()
    top = args.top or infer_top(interface, prompt)
    rc, log = self_check(
        args.task, source, top, interface, split_interface(interface), timeout_s=60,
    )
    print(log)
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
