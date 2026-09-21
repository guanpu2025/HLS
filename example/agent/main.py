"""Minimal HLS agent.

    generate -> csynth -> read the error -> regenerate

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
import time

from .llm import LLM, LLMError, extract_code
from .skills import load_skills, select
from .tools import HlsToolchain

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROMPT_DIR = os.path.join(HERE, "prompts")
SKILL_DIR = os.path.join(ROOT, "skill")

MAX_ROUNDS = int(os.environ.get("AGENT_MAX_ROUNDS", "3"))
DEADLINE_S = float(os.environ.get("AGENT_DEADLINE_S", "360"))
# 为写出结果预留的余量。
RESERVE_S = float(os.environ.get("AGENT_RESERVE_S", "20"))


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
        m = re.search(r"([A-Za-z_][\w.\-]*\.(?:h|hpp))", lines[0])
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


def solve_agent(llm: LLM, trace: Trace, prompt: str, interface: str, top: str) -> str:
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
    last_log = ""

    for rnd in range(1, MAX_ROUNDS + 1):
        remaining = DEADLINE_S - (time.time() - started) - RESERVE_S
        if remaining <= 0:
            trace.write(tool="budget", event="stop", round=rnd, reason="deadline")
            break

        messages = [{"role": "system", "content": system}]

        chosen = select(skills, prompt, last_log) if last_log else []
        if chosen:
            messages.append({
                "role": "system",
                "content": "以下技能与当前错误相关，按其中的步骤处理：\n\n"
                           + "\n\n".join(s.render() for s in chosen),
            })
            trace.write(tool="skills", event="inject", round=rnd,
                        selected=[s.name for s in chosen])

        user = build_task_block(prompt, interface)
        if last_log:
            user += "\n\n" + repair_tpl.replace("{{LOG}}", last_log) \
                                       .replace("{{CODE}}", best)

        messages.append({"role": "user", "content": user})

        t0 = time.time()
        try:
            result = llm.chat(messages)
        except LLMError as exc:
            trace.write(tool="llm", round=rnd, rc=1, excerpt=str(exc)[:500])
            break
        trace.write(
            tool="llm", round=rnd,
            tokens_in=result.tokens_in, tokens_out=result.tokens_out,
            elapsed_s=round(time.time() - t0, 2),
        )

        code = extract_code(result.text)
        if not code:
            trace.write(tool="extract", round=rnd, rc=1,
                        excerpt="no code block in reply")
            last_log = "上一轮回复中没有找到代码块。只输出一个 ```cpp 代码块，不要加解释。"
            continue

        best = code

        remaining = DEADLINE_S - (time.time() - started) - RESERVE_S
        if remaining <= 0:
            trace.write(tool="budget", event="stop", round=rnd, reason="deadline")
            break

        rc, log = hls.csynth(code, top, timeout_s=remaining, headers=headers)
        trace.write(tool="csynth", round=rnd, rc=rc, excerpt=log[:2000])

        if rc == 0:
            trace.write(tool="agent", event="accept", round=rnd)
            return code
        if rc < 0:
            # 工具链不可用或超时，无法验证，不再继续重试。
            trace.write(tool="agent", event="stop", round=rnd,
                        reason="no verification available")
            return code

        last_log = log

    return best


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

        top = args.top or infer_top(interface)
        code = solve_agent(llm, trace, prompt, interface, top)
    except Exception as exc:  # noqa: BLE001 -- never fail loudly, see run.sh
        trace.write(tool="agent", event="error", excerpt=f"{type(exc).__name__}: {exc}"[:500])
        print(f"agent: {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        with open(sol_path, "w", encoding="utf-8") as fh:
            fh.write(code or "")
        trace.write(tool="agent", event="done", bytes=len(code or ""))
        trace.close()

    return 0


def infer_top(interface: str) -> str:
    """Best-effort top function name from the declared signature."""
    import re
    m = re.search(r"\b([A-Za-z_]\w*)\s*\([^;{]*\)\s*;", interface or "")
    return m.group(1) if m else "top"


if __name__ == "__main__":
    raise SystemExit(main())
