"""Minimal HLS agent.

    generate -> selfcheck -> csynth (only if the check passed or skipped) -> repair

Three rounds, then stop. That is the whole control flow, and it is deliberately
the least interesting part of a competitive submission -- it exists so you have
something that runs end to end on day one, not so you can submit it.

    python -m agent.main --input <dir> --output <dir>

What is worth improving, roughly in order of payoff:

  * Self-verification. The official testbench is not handed to the agent, so
    csynth success says nothing about correctness. Most of the distance between
    L2 and L3 lives here.
  * Retry policy. This loop regenerates from scratch every round. Patching the
    previous attempt is usually cheaper and sometimes worse; which one wins
    depends on the failure class, and that is a measurable question.
  * Context management. summarize_log() keeps lines matching a fixed keyword
    list. A dataflow violation and a missing semicolon deserve different
    excerpts.
  * Budget allocation. Rounds are equal-cost here. They should not be -- the
    first round is the one most likely to succeed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time

from .llm import LLM, LLMError, extract_code, has_unclosed_fence, _strip_fence_lines
from .selfcheck import self_check
from .skills import load_skills, select
from .tools import HlsToolchain, classify

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROMPT_DIR = os.path.join(HERE, "prompts")
SKILL_DIR = os.path.join(ROOT, "skill")

DEADLINE_S = float(os.environ.get("AGENT_DEADLINE_S", "950"))
# Host g++ vs the local reference. On for the submitted run.sh.
SELF_CHECK = os.environ.get("AGENT_SELF_CHECK", "1") == "1"
# Functional rounds are cheap when self-check runs first, so allow more of them.
MAX_ROUNDS = int(os.environ.get("AGENT_MAX_ROUNDS", "6" if SELF_CHECK else "3"))
# 为写出结果预留的余量。
RESERVE_S = float(os.environ.get("AGENT_RESERVE_S", "20"))
# Conservative decode-rate seed (token/s). Overwritten after the first round
# from tokens_out/elapsed_s. Do not bake in a GPU-specific measurement.
TOKEN_RATE_INIT = float(os.environ.get("AGENT_TOKEN_RATE", "20"))
TOKEN_SAFETY = float(os.environ.get("AGENT_TOKEN_SAFETY", "0.8"))
MIN_TOKENS = int(os.environ.get("AGENT_MIN_TOKENS", "256"))
LLM_CTX = int(os.environ.get("LLM_CTX", "16384"))
MAX_CONTINUES = int(os.environ.get("AGENT_MAX_CONTINUES", "2"))
CONTINUE_MAX_LINES = 120
CONTINUE_MAX_CHARS = 4000
CONTINUE_MAX_LINE = 200
CONTINUE_HINT = (
    "上文是被截断的尾部，不是完整文件；从最后一行接着写，不要重复，不要重写整个文件。"
)


class Trace:
    """Append-only record of every model and tool call.

    评分所需，非可选项。
    """

    def __init__(self, path: str):
        self.path = path
        self._fh = open(path, "w", encoding="utf-8")

    def write(self, **fields) -> None:
        fields.setdefault("ts", round(time.time(), 3))
        self._fh.write(json.dumps(fields, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except OSError:
            pass


def read_prompt_file(name: str) -> str:
    with open(os.path.join(PROMPT_DIR, name), encoding="utf-8") as fh:
        return fh.read().strip()


def read_task(input_dir: str) -> tuple[str, str]:
    def _read(fname: str) -> str:
        path = os.path.join(input_dir, fname)
        if not os.path.isfile(path):
            return ""
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()

    return _read("prompt.txt"), _read("interface.txt")


def split_interface(interface: str) -> dict[str, str]:
    """Recover the header file from interface.txt.

    Its first line may be `// header: <name>`, with the header body following.
    The agent never sees the task directory -- only these two blobs of text --
    so reconstructing the header is the only way `#include "foo.h"` can resolve
    when csynth runs. Skip this and every check dies at `'foo.h' file not
    found`, which makes the whole generate-check-repair loop a no-op.

    Returns {} when the marker is absent; some tasks declare the signature
    inline instead of shipping a header.
    """
    if not interface.strip():
        return {}
    lines = interface.splitlines()
    name, body = None, lines

    # 首行若是注释，多半就是标出文件名的那行。实际见过两种写法，都要认：
    #   make-tasks.py 生成的评测题   `// header: fir11.h`
    #   仓库里的示例题               `// 头文件 fir11.h 已提供，直接 #include`
    if lines[0].lstrip().startswith("//"):
        # 文件名可以以数字开头（2mm.h）。从字母开始匹配会把 2mm.h 截成 mm.h。
        m = re.search(r"([A-Za-z0-9_][\w.\-]*\.(?:h|hpp))", lines[0])
        if m:
            name, body = m.group(1), lines[1:]

    # 没有注释标名字就从 include guard 反推：#ifndef FIR11_H -> fir11.h
    if name is None:
        m = re.search(r"#ifndef\s+([A-Za-z_]\w*?)_+H\b", interface)
        if m:
            name = m.group(1).lower() + ".h"

    text = "\n".join(body).strip("\n")
    if name is None or not text.strip():
        return {}
    return {name: text + "\n"}


def build_task_block(prompt: str, interface: str) -> str:
    return (
        "## 题目\n\n" + (prompt or "(empty)") +
        "\n\n## 顶层接口（签名不得改动）\n\n```cpp\n" + (interface or "(empty)") + "\n```\n"
    )


# 基线由赛事方的 ../baseline.py 实现，不在此处。


def _error_excerpt(log: str, limit: int = 1200) -> str:
    """Keep the first distinct ERROR lines. Warnings are not repair input."""
    lines = [ln.strip() for ln in log.splitlines() if "ERROR" in ln or "error:" in ln]
    if not lines:
        lines = [ln.strip() for ln in log.splitlines() if ln.strip()][:8]
    text = "\n".join(dict.fromkeys(lines))
    return text[:limit]


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n/* ... truncated for context limit ... */\n"


# Short skills injected only for the matching failure class. The long
# hls-top-interface-contract document stays on disk; sending it on a repair
# round overflows the 16384-token context.
_SKILL_FOR_KIND = {
    "array_type": "hls-array-typedef",
    "interface": "hls-interface-contract",
    "header": "hls-no-host-headers",
    "functional": "hls-functional-selfcheck",
    "timeout": "hls-csynth-timeout-partition",
}


def _choose_skills(skills, kind: str, prompt: str, log: str):
    forced_name = _SKILL_FOR_KIND.get(kind, "")
    forced = [s for s in skills if s.name == forced_name]
    chosen = select(skills, prompt, log) if log else []
    blocked = set(_SKILL_FOR_KIND.values())
    if forced_name == "hls-interface-contract":
        blocked.add("hls-top-interface-contract")
    chosen = forced + [s for s in chosen if s.name not in blocked]
    if not forced:
        chosen = [s for s in chosen if s.name not in _SKILL_FOR_KIND.values()]
    return chosen[:2]


def _repair_hint(kind: str) -> str:
    """One-line instruction for the class returned by tools.classify."""
    return {
        "interface": "失败类别 interface：只改 #include 和顶层函数签名，不要改算法。",
        "unsynth": "失败类别 unsynth：去掉动态分配、std::vector、std::string 和递归，保留算法。",
        "header": "失败类别 header：删掉 stdio、cstdlib、cmath 等主机头文件及其调用，只保留题目头文件。",
        "array_type": "失败类别 array_type：头文件里的类型可能是数组。按下标读写元素，不要把整个数组当作整数、结构体或可直接赋值的值。",
        "pragma": "失败类别 pragma：先删除 #pragma HLS，不要把 PIPELINE 放在最外层循环之前。",
        "functional": "失败类别 functional：保持接口不变，按参考的更新式改计算，让 dut 变成 ref。不要只改 pragma。",
        "timeout": "失败类别 timeout：综合超时。删掉大数组上的 ARRAY_PARTITION complete 和 UNROLL，不要靠加 PIPELINE 来修。",
    }.get(kind, "失败类别 other：只改日志里第一条错误对应的部分，不要整份重写。")


_REPAIR_FUNCTIONAL = """\
## 上一轮的实现

```cpp
{{CODE}}
```

## 小测试台的结果

```
{{LOG}}
```

## 本轮要做的事

1. 这里没有 `ERROR:`。上面的 `inputs` 是输入，`dut` 是你的输出，`ref` 是正确输出。
2. 按参考实现的更新式改计算，让 `dut` 变成 `ref`。不要只改被点名的那一个输出，也不要只改 pragma。
3. `float_n` / `n` 是样本数，均值除以它；协方差除以 `float_n - 1`。原地数组（例如 `data[]`）要按参考那样改写，常见是减去均值。
4. 矩阵乘的中间量若带 `alpha`，先乘进中间量，后面不要再乘一次。
5. 若 `char` 序列取值是 0–3，碱基配对是 `(seq[i] + seq[j]) == 3`，不要用 `'A'`/`'T'`/`'G'`/`'C'`。
6. 顶层函数签名不要动。这一轮的代码必须和上一轮不同，不能把上一轮原样输出。若提示交回了同一份代码，必须换更新式（换循环边界、换递推、换配对条件），不要只改同一行。

输出完整文件，只输出一个 ```cpp 代码块，块外不要有任何文字。
"""

_REPAIR_TIMEOUT = """\
## 上一轮的实现

```cpp
{{CODE}}
```

## 综合结果

```
{{LOG}}
```

## 本轮要做的事

1. 综合超时，日志里没有 `ERROR:`。不要把上一轮原样输出。
2. 删掉大数组上的 `#pragma HLS ARRAY_PARTITION complete` 和 `UNROLL`。
3. 把变长 `while` 改成有常数上界的 `for`。不要靠加 `PIPELINE` 来修。
4. 顶层函数签名不要动。

输出完整文件，只输出一个 ```cpp 代码块，块外不要有任何文字。
"""


def _observed_mismatch(log: str) -> tuple[str, str, str] | None:
    """Return the failing output, the inputs line, and the dut/ref line.

    Used to notice when a repair edited the source but left this result unchanged.
    """
    output = ""
    inputs = ""
    values = ""
    for raw in log.splitlines():
        line = raw.strip()
        if not output and line.startswith("self-check failed:") and "mismatch" in line:
            output = line.removeprefix("self-check failed:").replace("mismatch", "").strip()
        elif not inputs and line.startswith("inputs"):
            inputs = line
        elif not values and " dut=" in line and " ref=" in line:
            values = line
    if not values:
        return None
    return output, inputs, values


def _repair_template(kind: str) -> str:
    if kind == "functional":
        return _REPAIR_FUNCTIONAL
    if kind == "timeout":
        return _REPAIR_TIMEOUT
    return ""


def _round_max_tokens(remaining_s: float, rate: float, cap: int) -> int | None:
    """Map leftover wall clock to this round's completion budget.

    LLM_MAX_TOKENS is a cap, not a target. None means skip generation.
    """
    n = min(int(cap), int(remaining_s * rate * TOKEN_SAFETY))
    if n < MIN_TOKENS:
        return None
    return n


def _atomic_write(path: str, text: str) -> None:
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".sol_", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write_solution(output_dir: str, text: str) -> None:
    if not output_dir:
        return
    _atomic_write(os.path.join(output_dir, "solution.cpp"), text or "")


def _has_top_function(code: str, top: str) -> bool:
    if not top or not code:
        return False
    return re.search(rf"\b{re.escape(top)}\s*\(", code) is not None


def _is_fresh_restart(code: str, top: str) -> bool:
    """Continuation that restarts the file: #include plus the top function."""
    return bool(code.lstrip().startswith("#include") and _has_top_function(code, top))


def _stitch_code(prefix: str, extra: str) -> str:
    if not extra.strip():
        return prefix if not prefix or prefix.endswith("\n") else prefix + "\n"
    if not prefix.strip():
        return extra if extra.endswith("\n") else extra + "\n"
    body = prefix.rstrip("\n") + "\n" + extra.lstrip("\n")
    return body if body.endswith("\n") else body + "\n"


def _continue_tail(code: str, max_chars: int = CONTINUE_MAX_CHARS) -> str:
    """Keep a short, line-bounded suffix of a truncated fragment."""
    lines = [ln for ln in (code or "").splitlines() if len(ln) <= CONTINUE_MAX_LINE]
    lines = lines[-CONTINUE_MAX_LINES:]
    text = "\n".join(lines)
    while lines and len(text) > max_chars:
        lines = lines[1:]
        text = "\n".join(lines)
    return text


def _continue_user(code: str) -> str:
    overhead = len("\n\n" + CONTINUE_HINT + "\n")
    tail = _continue_tail(code, max_chars=max(0, CONTINUE_MAX_CHARS - overhead))
    if tail:
        return tail.rstrip() + "\n\n" + CONTINUE_HINT + "\n"
    return CONTINUE_HINT + "\n"


def _round_csynth_budget(remaining: float, rnd: int) -> float:
    """Share the time still left with later rounds.

    The csynth call used to receive the whole leftover deadline, so one 320s
    timeout ended the task before a repair round existed.
    """
    later = MAX_ROUNDS - rnd
    if later <= 0 or remaining <= 0:
        return remaining
    return max(1.0, remaining / (later + 1))


def _save_round(output_dir: str, rnd: int, name: str, text: str) -> str:
    """Keep each attempt on disk. The trace only stores a short excerpt."""
    folder = os.path.join(output_dir, "rounds")
    os.makedirs(folder, exist_ok=True)
    rel = os.path.join("rounds", f"r{rnd}.{name}")
    with open(os.path.join(output_dir, rel), "w", encoding="utf-8") as fh:
        fh.write(text or "")
    return rel


def solve_agent(llm: LLM, trace: Trace, prompt: str, interface: str, top: str,
                task_dir: str = "", output_dir: str = "") -> str:
    hls = HlsToolchain()
    trace.write(
        tool="env", vitis_available=hls.available,
        vitis=os.path.basename(hls.exe) if hls.exe else None,
        reason=hls.reason or None,
    )

    skills = load_skills(SKILL_DIR)
    trace.write(tool="skills", loaded=[s.name for s in skills])

    headers = split_interface(interface)
    trace.write(tool="headers", recovered=list(headers))

    system = read_prompt_file("system.md")
    repair_tpl = read_prompt_file("repair.md")

    started = time.time()
    best = ""
    kept = ""
    compiled = ""
    last_log = ""
    last_kind = ""
    bump_temp = False
    token_rate = TOKEN_RATE_INIT
    pending_continue = False
    continue_src = ""
    continues_used = 0
    longest = ""
    best_is_trunc = False

    for rnd in range(1, MAX_ROUNDS + 1):
        remaining = DEADLINE_S - (time.time() - started) - RESERVE_S
        if remaining <= 0:
            trace.write(tool="budget", event="stop", round=rnd, reason="deadline")
            break

        round_max = _round_max_tokens(remaining, token_rate, llm.max_tokens)
        if round_max is None:
            trace.write(
                tool="budget", event="stop", round=rnd, reason="token_budget",
                remaining_s=round(remaining, 2), token_rate=token_rate,
                max_tokens=0,
            )
            break
        trace.write(
            tool="budget", event="round", round=rnd,
            max_tokens=round_max, token_rate=token_rate,
            remaining_s=round(remaining, 2),
        )

        messages = [{"role": "system", "content": system}]

        if pending_continue:
            overhead = len("\n\n" + CONTINUE_HINT + "\n")
            tail = _continue_tail(
                continue_src, max_chars=max(0, CONTINUE_MAX_CHARS - overhead),
            )
            carried_lines = len(tail.splitlines()) if tail else 0
            trace.write(
                tool="agent", event="continue", round=rnd,
                continues=continues_used + 1,
                carried_chars=len(tail),
                carried_lines=carried_lines,
            )
            user = _continue_user(continue_src)
        else:
            chosen = _choose_skills(skills, last_kind, prompt, last_log)
            if chosen:
                # One system message only. Qwen's template rejects a second one
                # with "System message must be at the beginning."
                messages[0]["content"] += (
                    "\n\n以下技能与当前错误相关，按其中的步骤处理：\n\n"
                    + "\n\n".join(s.render() for s in chosen)
                )
                trace.write(tool="skills", event="inject", round=rnd,
                            selected=[s.name for s in chosen])

            if last_log:
                # Repair rounds omit the long task statement and clip the previous
                # kernel. des overflowed the context when both were sent.
                template = _repair_template(last_kind) or repair_tpl
                user = (
                    "## 顶层接口（签名不得改动）\n\n```cpp\n" + (interface or "") + "\n```\n\n"
                    + _repair_hint(last_kind) + "\n\n"
                    + template.replace("{{LOG}}", _error_excerpt(last_log))
                              .replace("{{CODE}}", _clip(best, 4000))
                )
            else:
                user = build_task_block(prompt, interface)

        messages.append({"role": "user", "content": user})

        t0 = time.time()
        if pending_continue or rnd == 1:
            temperature = 0.0
        elif bump_temp:
            temperature = 0.5
        else:
            temperature = llm.temperature
        try:
            result = llm.chat(messages, temperature=temperature, max_tokens=round_max)
        except LLMError as exc:
            trace.write(tool="llm", round=rnd, rc=1, excerpt=str(exc)[:500])
            break
        elapsed = time.time() - t0
        elapsed_s = round(elapsed, 2)
        if rnd == 1 and result.tokens_out > 0 and elapsed > 0:
            token_rate = result.tokens_out / elapsed
        trace.write(
            tool="llm", round=rnd,
            tokens_in=result.tokens_in, tokens_out=result.tokens_out,
            elapsed_s=elapsed_s,
            temperature=temperature,
            max_tokens=round_max,
            token_rate=token_rate,
        )

        unclosed = has_unclosed_fence(result.text)
        hit_ctx = LLM_CTX > 0 and (result.tokens_in + result.tokens_out) >= LLM_CTX
        hit_max = round_max > 0 and result.tokens_out >= round_max
        if unclosed or hit_ctx:
            trace.write(
                tool="extract", event="truncated", round=rnd,
                unclosed_fence=unclosed, hit_ctx=hit_ctx,
                tokens_in=result.tokens_in, tokens_out=result.tokens_out,
                ctx_limit=LLM_CTX,
            )

        piece = extract_code(result.text)
        if pending_continue and not piece:
            piece = _strip_fence_lines(result.text)
        if not piece:
            trace.write(tool="extract", round=rnd, rc=1,
                        excerpt="no code block in reply")
            last_log = "上一轮回复中没有找到代码块。只输出一个 ```cpp 代码块，不要加解释。"
            pending_continue = False
            continue

        from_continue = pending_continue
        if pending_continue:
            continues_used += 1
            if _is_fresh_restart(piece, top):
                code = piece if piece.endswith("\n") else piece + "\n"
            else:
                code = _stitch_code(continue_src, piece)
        else:
            code = piece if piece.endswith("\n") else piece + "\n"

        is_trunc = unclosed or hit_max

        if is_trunc:
            if len(code) > len(longest):
                longest = code
            if output_dir:
                _save_round(output_dir, rnd, "cpp", code)
            if compiled:
                # Continue-stitch (or its truncated prefix) must not clobber a
                # host-compilable candidate. rc=1 counts; selfcheck was not run.
                trace.write(tool="agent", event="keep_compiled", round=rnd)
                _write_solution(output_dir, kept or compiled)
            elif (not best) or (best_is_trunc and len(code) >= len(best)):
                best = code
                best_is_trunc = True
                _write_solution(output_dir, kept or best)
            if continues_used >= MAX_CONTINUES:
                trace.write(
                    tool="agent", event="stop", round=rnd,
                    reason="max_continues", continues=continues_used,
                )
                break
            pending_continue = True
            continue_src = code
            continue

        pending_continue = False
        continue_src = ""
        best_is_trunc = False
        if len(code) > len(longest):
            longest = code

        already_checked = False
        src = -1
        slog = ""

        if best and code.strip() == best.strip():
            bump_temp = True
            trace.write(tool="agent", event="identical", round=rnd, temperature=0.5)
            if output_dir:
                _save_round(output_dir, rnd, "cpp", code)
            _write_solution(output_dir, kept or best)
            if "换更新式" not in last_log:
                last_log += (
                    "\n你交回了同一份代码。必须换一种更新式（换循环边界、换递推、"
                    "换配对条件），不要只改同一行，不能原样输出上一轮的实现。"
                )
            if rnd < MAX_ROUNDS:
                continue
            trace.write(
                tool="agent", event="csynth_anyway", round=rnd,
                reason="identical_last",
            )
        elif from_continue:
            bump_temp = False
            if output_dir:
                _save_round(output_dir, rnd, "cpp", code)
            remaining = DEADLINE_S - (time.time() - started) - RESERVE_S
            accept = False
            if remaining > 0 and SELF_CHECK and task_dir:
                src, slog = self_check(
                    task_dir, code, top, interface, headers, timeout_s=remaining,
                )
                already_checked = True
                check_path = (
                    _save_round(output_dir, rnd, "selfcheck.txt", slog)
                    if output_dir else ""
                )
                trace.write(
                    tool="selfcheck", round=rnd, rc=src,
                    excerpt=slog[:2000], log_path=check_path or None,
                )
                if src in (0, 1):
                    compiled = code
                    accept = True
            if accept:
                best = code
                _write_solution(output_dir, kept or best)
            elif compiled:
                trace.write(tool="agent", event="keep_compiled", round=rnd)
                _write_solution(output_dir, kept or compiled)
                if remaining <= 0:
                    trace.write(
                        tool="budget", event="stop", round=rnd, reason="deadline",
                    )
                    break
                continue
            else:
                best = code
                _write_solution(output_dir, kept or best)
        else:
            bump_temp = False
            best = code
            if output_dir:
                _save_round(output_dir, rnd, "cpp", code)
            _write_solution(output_dir, kept or best)

        remaining = DEADLINE_S - (time.time() - started) - RESERVE_S
        if remaining <= 0:
            trace.write(tool="budget", event="stop", round=rnd, reason="deadline")
            break

        func_fail = False
        if already_checked:
            check_src, check_slog = src, slog
        elif SELF_CHECK and task_dir:
            check_src, check_slog = self_check(
                task_dir, code, top, interface, headers, timeout_s=remaining,
            )
            check_path = (
                _save_round(output_dir, rnd, "selfcheck.txt", check_slog)
                if output_dir else ""
            )
            trace.write(
                tool="selfcheck", round=rnd, rc=check_src,
                excerpt=check_slog[:2000], log_path=check_path or None,
            )
            if check_src in (0, 1):
                compiled = code
        else:
            check_src, check_slog = None, ""
        if check_src is not None and check_src > 0:
            func_fail = True
            observed = _observed_mismatch(check_slog)
            previous = (
                _observed_mismatch(last_log) if last_kind == "functional" else None
            )
            last_kind = "functional"
            last_log = check_slog.rstrip()
            if observed and observed == previous:
                output = observed[0] or "这个输出"
                last_log += f"\n上次的修改没有改变 {output}，请改写这个输出的计算。"
            # Cheap functional rounds skip csynth. The last round always
            # synthesizes, including when the model repeated the last kernel.
            if rnd < MAX_ROUNDS:
                trace.write(
                    tool="agent", event="skip_csynth", round=rnd,
                    reason="functional",
                )
                continue

        remaining = DEADLINE_S - (time.time() - started) - RESERVE_S
        if remaining <= 0:
            trace.write(tool="budget", event="stop", round=rnd, reason="deadline")
            break

        if func_fail:
            synth_timeout = _round_csynth_budget(remaining, rnd)
        else:
            # Self-check already passed (or was skipped). Spend the remaining
            # wall clock on csynth, keep ~40s for one pragma repair.
            synth_timeout = max(1.0, remaining - 40.0)
        rc, log = hls.csynth(
            code, top, timeout_s=synth_timeout, headers=headers,
        )
        kind = classify(code, log)
        csynth_path = _save_round(output_dir, rnd, "csynth.txt", log) if output_dir else ""
        trace.write(tool="csynth", round=rnd, rc=rc, failure=kind,
                    excerpt=log[:2000], log_path=csynth_path or None)

        if rc == 0:
            kept = code
            _write_solution(output_dir, kept)
            if func_fail:
                break
            trace.write(tool="agent", event="accept", round=rnd)
            return code
        if rc < 0 and kind != "timeout":
            # 工具链不可用，无法验证，不再继续重试。综合超时仍重试，前提是上面把
            # 本轮时限封顶，后面的轮次还剩时间。
            trace.write(tool="agent", event="stop", round=rnd,
                        reason="no verification available", failure=kind)
            return kept or code

        last_kind = kind
        last_log = log

    if kept and kept.strip() != (best or "").strip():
        trace.write(tool="agent", event="revert", reason="keep_last_csynth")
        _write_solution(output_dir, kept)
        return kept
    handoff = kept or best
    if best_is_trunc and len(longest) > len(handoff or ""):
        handoff = longest
    _write_solution(output_dir, handoff)
    return handoff


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="minimal HLS agent")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--top", default=os.environ.get("HLS_TOP", ""),
                    help="top function name; inferred from interface.txt if absent")
    args = ap.parse_args(argv)

    os.makedirs(args.output, exist_ok=True)
    sol_path = os.path.join(args.output, "solution.cpp")
    trace = Trace(os.path.join(args.output, "trace.jsonl"))

    code = ""
    try:
        prompt, interface = read_task(args.input)
        llm = LLM()
        trace.write(tool="agent", event="start", mode="agent",
                    llm=llm.describe(), deadline_s=DEADLINE_S)

        top = args.top or infer_top(interface, prompt)
        code = solve_agent(llm, trace, prompt, interface, top, args.input, args.output)
    except Exception as exc:  # noqa: BLE001 -- never fail loudly, see run.sh
        trace.write(tool="agent", event="error", excerpt=f"{type(exc).__name__}: {exc}"[:500])
        print(f"agent: {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        if code:
            _atomic_write(sol_path, code)
        elif not os.path.isfile(sol_path) or os.path.getsize(sol_path) == 0:
            _atomic_write(sol_path, "")
        trace.write(tool="agent", event="done", bytes=len(code or ""))
        trace.close()

    return 0


_TOP_IN_PROMPT = re.compile(r"Top-Level Function:\s*`([A-Za-z_]\w*)`")
# 只认带返回类型的函数声明。跳过 #define，避免 STRING_SIZE、getSBoxValue 被当成顶层。
_PROTO = re.compile(
    r"^\s*(?:[\w:*&]+\s+)+([A-Za-z_]\w*)\s*\([^;]*\)\s*;\s*$",
    re.M,
)


def infer_top(interface: str, prompt: str = "") -> str:
    """Top function name from the prompt, else the first real prototype."""
    m = _TOP_IN_PROMPT.search(prompt or "")
    if m:
        return m.group(1)
    lines = [
        ln for ln in (interface or "").splitlines()
        if not ln.strip().startswith("#")
    ]
    names = _PROTO.findall("\n".join(lines))
    return names[0] if names else "top"


if __name__ == "__main__":
    raise SystemExit(main())
