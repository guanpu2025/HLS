"""对一份 HLS 解给出分级结果。

    L1 可解析  →  L2 可编译  →  L3 可运行  →  L4 可综合

严格递进：低一级没过，高一级就不算。得分取达到的最高级别对应的系数。

    python3 judge.py --task ../tasks/ex01_fir11 --solution /tmp/out/solution.cpp

本文件是 judge/hls-judge 的适配层，后者与赛事方正式评测同源，见 judge/PROVENANCE.md。
本层做三件事：

  1. 把本仓库的任务布局（task.json + 头文件 + 测试台）交给 hls-judge 的
     --kernel-dir 接口；
  2. 把 hls-judge 的输出字段翻译成 score.py 期望的字段；
  3. 把环境类判定（授权、题目损坏）标成 tool_error，由 score.py 排除出算分。

判分逻辑不在此处重新实现，否则自测与正式评测会产生分歧。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HLS_JUDGE = os.path.join(HERE, "judge", "hls-judge")

COEFFICIENT = {0: 0.0, 1: 0.1, 2: 0.2, 3: 0.8, 4: 1.0}

SCRATCH = os.environ.get("SELFTEST_TMP", "/tmp")

# 环境或题目异常的判定结果，由 score.py 排除出平均分。
TOOL_VERDICTS = {
    "LICENSE_ERROR":  "Vitis 未能签出授权（2026.1 的 HLS 需要席位）",
    "FIXTURE_ERROR":  "题目自带的测试台或参考实现有问题，与待测代码无关",
    "NO_TOP":         "题目目录缺 top.txt",
    "NO_TB":          "题目目录缺 *_tb.cpp",
    "JUDGE_ERROR":    "判定器本身异常退出",
}


def load_task(task_dir: str) -> dict:
    with open(os.path.join(task_dir, "task.json"), encoding="utf-8") as fh:
        return json.load(fh)


def judge(task_dir: str, solution_path: str, outdir: str | None = None,
          timeout_s: float = 1800.0) -> dict:
    task = load_task(task_dir)
    top = task["top"]
    result = {
        "task_id": task.get("task_id", os.path.basename(task_dir)),
        "top": top,
        "level": 0,
        "coefficient": 0.0,
        "stages": {"parse": False, "compile": False, "run": False, "synth": False},
        "tool_error": None,
        "elapsed_s": 0.0,
    }

    t0 = time.time()

    try:
        with open(solution_path, encoding="utf-8", errors="replace") as fh:
            source = fh.read()
    except OSError as exc:
        result["tool_error"] = f"读不到解文件：{exc}"
        result["elapsed_s"] = round(time.time() - t0, 1)
        return result

    if not source.strip():
        # 空解表示未能求解，属于 L0。
        result["elapsed_s"] = round(time.time() - t0, 1)
        return result

    if not os.path.isfile(HLS_JUDGE):
        result["tool_error"] = f"找不到判定器 {HLS_JUDGE}"
        result["elapsed_s"] = round(time.time() - t0, 1)
        return result

    work = os.path.join(SCRATCH, f"judge_{result['task_id']}_{os.getpid()}")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)

    # hls-judge 的 --dut 需要 .cpp 文件，落到 work 下统一命名。
    dut = os.path.join(work, f"{top}.cpp")
    with open(dut, "w", encoding="utf-8") as fh:
        fh.write(source)

    part = task.get("part", "xczu3eg-sbva484-1-e")
    period = float(task.get("period_ns", 5))
    js = os.path.join(work, "verdict.json")

    cmd = [
        sys.executable, HLS_JUDGE,
        "--dut", dut,
        "--kernel-dir", os.path.abspath(task_dir),
        "--workdir", os.path.join(work, "w"),
        "--level", "4",
        "--part", part,
        "--clock-ns", str(period),
        "--json", js,
        "--clean", "--quiet",
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_s, errors="replace")
        raw = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        result["tool_error"] = f"判定超时（>{timeout_s:.0f}s）"
        result["elapsed_s"] = round(time.time() - t0, 1)
        _cleanup(work, result)
        return result

    _dump(outdir, f"{result['task_id']}.judge.log", raw)

    try:
        with open(js, encoding="utf-8") as fh:
            verdict = json.load(fh)
    except (OSError, json.JSONDecodeError):
        result["tool_error"] = TOOL_VERDICTS["JUDGE_ERROR"]
        result["elapsed_s"] = round(time.time() - t0, 1)
        _cleanup(work, result)
        return result

    _translate(verdict, result)
    result["elapsed_s"] = round(time.time() - t0, 1)
    _cleanup(work, result)
    return result


def _translate(verdict: dict, result: dict) -> None:
    """把 hls-judge 的输出翻译成 score.py 认的字段。"""
    v = verdict.get("verdict")

    if v in TOOL_VERDICTS:
        # 环境或题目问题：级别留 0，打上 tool_error，由 score.py 排除出平均。
        result["tool_error"] = verdict.get("note") or TOOL_VERDICTS[v]
        return

    level = verdict.get("level")
    if level is None:
        result["tool_error"] = verdict.get("note") or TOOL_VERDICTS["JUDGE_ERROR"]
        return

    result["level"] = level
    result["coefficient"] = COEFFICIENT.get(level, 0.0)

    # 将 hls-judge 各阶段的 rc/耗时转为四个布尔。
    # 分级本身是严格递进的，直接由级别反推，不必二次解析日志。
    for lvl, key in ((1, "parse"), (2, "compile"), (3, "run"), (4, "synth")):
        result["stages"][key] = level >= lvl

    if verdict.get("note"):
        result["note"] = verdict["note"]


def _cleanup(work: str, result: dict) -> None:
    if os.environ.get("SELFTEST_KEEP_WORK") == "1":
        result["work_dir"] = work
    else:
        shutil.rmtree(work, ignore_errors=True)


def _dump(outdir: str | None, name: str, text: str) -> None:
    if not outdir:
        return
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, name), "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="判定一份 HLS 解，L0–L4")
    ap.add_argument("--task", required=True, help="含 task.json 的题目目录")
    ap.add_argument("--solution", required=True, help="solution.cpp 路径")
    ap.add_argument("--outdir", default=None, help="工具日志写到哪")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--timeout", type=float, default=1800.0)
    args = ap.parse_args(argv)

    res = judge(args.task, args.solution, args.outdir, args.timeout)

    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=2)

    label = f"L{res['level']}"
    stages = "".join(
        c if res["stages"][k] else "-"
        for c, k in (("P", "parse"), ("C", "compile"), ("R", "run"), ("S", "synth"))
    )
    note = f"  [{res['tool_error']}]" if res["tool_error"] else ""
    print(f"{res['task_id']:<20} {label}  {stages}  coeff={res['coefficient']:.1f}  "
          f"{res['elapsed_s']:.0f}s{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
