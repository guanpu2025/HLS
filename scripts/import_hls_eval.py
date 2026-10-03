#!/usr/bin/env python3
"""Convert sharc-lab/HLS-Eval kernels into hlsagent2026/tasks/ layout.

Usage:
  python3 scripts/import_hls_eval.py
  python3 scripts/import_hls_eval.py --src /path/to/hls-eval/hls_eval_data
  python3 scripts/import_hls_eval.py --clean-he   # remove previously imported he_* tasks
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = Path("/data/guanpu/FPGA/hls-eval/hls_eval_data")
DEFAULT_DST = ROOT / "tasks"

PART = "xczu3eg-sbva484-1-e"
PERIOD_NS = 5

SUITE_ALIAS = {
    "hls_polybench__fixed__small": "polybench_fixed",
}

SKIP_NAME_RE = re.compile(r"__WIP$")

# Copied into the task dir for the judge (hls-judge prepare globs these).
DATA_GLOBS = ("*.data", "tb_data*.txt", "tb_data*.json")


def suite_alias(suite: str) -> str:
    return SUITE_ALIAS.get(suite, suite)


def task_id_for(suite: str, kernel: str) -> str:
    return f"he_{suite_alias(suite)}_{kernel}"


def discover_kernels(src: Path) -> list[Path]:
    out: list[Path] = []
    for cfg in sorted(src.rglob("hls_eval_config.toml")):
        d = cfg.parent
        if SKIP_NAME_RE.search(d.name) or "__WIP" in d.parts:
            continue
        out.append(d)
    return out


def pick_one(paths: list[Path], kind: str, d: Path) -> Path:
    if not paths:
        raise FileNotFoundError(f"{d}: missing {kind}")
    if len(paths) > 1:
        raise RuntimeError(f"{d}: expected one {kind}, found {[p.name for p in paths]}")
    return paths[0]


def collect_extras(d: Path) -> list[Path]:
    files: dict[str, Path] = {}
    for pat in DATA_GLOBS:
        for p in d.glob(pat):
            if p.is_file():
                files[p.name] = p
    # Prefer tb_data_hls.txt over tb_data.txt when both exist — keep both;
    # hls-judge prefers tb_data_hls.txt then tb_data.txt.
    return [files[k] for k in sorted(files)]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def convert_one(src_dir: Path, dst_root: Path) -> str:
    suite = src_dir.parent.name
    kernel = src_dir.name
    tid = task_id_for(suite, kernel)
    dst = dst_root / tid

    top = (src_dir / "top.txt").read_text(encoding="utf-8", errors="replace").strip()
    if not top:
        raise RuntimeError(f"{src_dir}: empty top.txt")

    header = pick_one(
        sorted(src_dir.glob("*.h")) + sorted(src_dir.glob("*.hpp")),
        "header",
        src_dir,
    )
    tb = pick_one(sorted(src_dir.glob("*_tb.cpp")), "testbench", src_dir)
    refs = sorted(
        p for p in src_dir.glob("*.cpp") if not p.name.endswith("_tb.cpp")
    )
    ref = pick_one(refs, "reference cpp", src_dir)
    prompt = (src_dir / "kernel_description.md").read_text(
        encoding="utf-8", errors="replace"
    )
    header_body = header.read_text(encoding="utf-8", errors="replace")
    extras = collect_extras(src_dir)

    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    (dst / "reference").mkdir()

    write_text(dst / "prompt.txt", prompt)
    write_text(dst / "top.txt", top)
    write_text(dst / header.name, header_body)
    write_text(
        dst / "interface.txt",
        f"// header: {header.name}\n"
        f"// 头文件 {header.name} 已提供，直接 #include，不要重复定义其中的类型、宏与常量数组。\n"
        f"\n"
        f"{header_body.lstrip()}".rstrip() + "\n",
    )
    shutil.copy2(tb, dst / tb.name)
    shutil.copy2(ref, dst / "reference" / ref.name)
    for extra in extras:
        shutil.copy2(extra, dst / extra.name)

    task = {
        "task_id": tid,
        "top": top,
        "part": PART,
        "period_ns": PERIOD_NS,
        "header": header.name,
        "testbench": tb.name,
        "extra_files": [p.name for p in extras],
        "reference": f"reference/{ref.name}",
        "source": {
            "dataset": "HLS-Eval",
            "suite": suite,
            "kernel": kernel,
            "path": str(src_dir),
        },
    }
    write_text(dst / "task.json", json.dumps(task, ensure_ascii=False, indent=2) + "\n")
    return tid


def clean_he(dst_root: Path) -> int:
    n = 0
    for p in sorted(dst_root.glob("he_*")):
        if p.is_dir() and (p / "task.json").is_file():
            shutil.rmtree(p)
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--dst", type=Path, default=DEFAULT_DST)
    ap.add_argument("--clean-he", action="store_true",
                    help="remove existing he_* tasks before import")
    ap.add_argument("--suites", nargs="*", default=None,
                    help="optional suite filter, e.g. c2hlsc machsuite")
    args = ap.parse_args()

    if not args.src.is_dir():
        raise SystemExit(f"HLS-Eval data not found: {args.src}")

    args.dst.mkdir(parents=True, exist_ok=True)
    if args.clean_he:
        removed = clean_he(args.dst)
        print(f"removed {removed} existing he_* tasks")

    kernels = discover_kernels(args.src)
    if args.suites:
        want = set(args.suites)
        kernels = [k for k in kernels if k.parent.name in want]

    ok, fail = [], []
    for k in kernels:
        try:
            tid = convert_one(k, args.dst)
            ok.append(tid)
            print(f"OK  {tid}")
        except Exception as exc:  # noqa: BLE001 — batch import report
            fail.append((str(k), str(exc)))
            print(f"FAIL {k}: {exc}")

    print(f"\nimported {len(ok)} / {len(kernels)}; failed {len(fail)}")
    if fail:
        for path, err in fail:
            print(f"  - {path}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
