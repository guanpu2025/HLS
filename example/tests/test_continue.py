"""Truncated replies are continued, not restarted; short fragments do not win."""

from __future__ import annotations

from agent.llm import LLMResult
from agent.main import CONTINUE_HINT, Trace, _continue_user, solve_agent

from test_solution_persist import FakeHls


class ScriptLLM:
    max_tokens = 8192
    temperature = 0.2

    def __init__(self, replies: list[tuple[str, int]]):
        self.replies = replies
        self.calls = 0
        self.users: list[str] = []

    def chat(self, messages, temperature=None, max_tokens=None):
        self.users.append(messages[-1]["content"])
        text, tokens_out = self.replies[self.calls]
        self.calls += 1
        return LLMResult(text=text, tokens_in=10, tokens_out=tokens_out)


def _run(tmp_path, monkeypatch, llm, max_rounds=6):
    import agent.main as main_mod

    monkeypatch.setattr(main_mod, "HlsToolchain", lambda: FakeHls())
    monkeypatch.setattr(main_mod, "SELF_CHECK", False)
    monkeypatch.setattr(main_mod, "MAX_ROUNDS", max_rounds)
    monkeypatch.setattr(main_mod, "DEADLINE_S", 950.0)

    out = tmp_path / "out"
    out.mkdir()
    trace = Trace(str(out / "trace.jsonl"))
    try:
        solve_agent(
            llm, trace,
            prompt="Top-Level Function: `top`",
            interface="void top();",
            top="top",
            task_dir="",
            output_dir=str(out),
        )
    finally:
        trace.close()
    return out


def test_continue_stitches_second_half(tmp_path, monkeypatch):
    first = '```cpp\n#include "k.h"\nvoid top() {\n    int a = 1;\n'
    second = "```cpp\n    int b = 2;\n}\n```\n"
    llm = ScriptLLM([(first, 8192), (second, 40)])
    out = _run(tmp_path, monkeypatch, llm, max_rounds=2)
    sol = (out / "solution.cpp").read_text(encoding="utf-8")
    assert '#include "k.h"' in sol
    assert sol.count("#include") == 1
    assert "int a = 1" in sol
    assert "int b = 2" in sol
    assert CONTINUE_HINT in llm.users[1]
    assert "int a = 1" in llm.users[1]
    events = [
        __import__("json").loads(ln)
        for ln in (out / "trace.jsonl").read_text().splitlines() if ln
    ]
    cont = [e for e in events if e.get("tool") == "agent" and e.get("event") == "continue"]
    assert cont and cont[0].get("round") == 2
    assert "carried_chars" in cont[0] and "carried_lines" in cont[0]
    assert cont[0]["carried_chars"] <= 4000


def test_continue_fresh_include_replaces(tmp_path, monkeypatch):
    first = '```cpp\n#include "k.h"\nvoid top() {\n    int a = 1;\n'
    restart = '```cpp\n#include "k.h"\nvoid top() { int a = 2; }\n```\n'
    llm = ScriptLLM([(first, 8192), (restart, 40)])
    out = _run(tmp_path, monkeypatch, llm, max_rounds=2)
    sol = (out / "solution.cpp").read_text(encoding="utf-8")
    assert "int a = 2" in sol
    assert "int a = 1" not in sol
    assert sol.count("#include") == 1


def test_shorter_truncated_does_not_overwrite_longer(tmp_path, monkeypatch):
    long_body = '#include "k.h"\nvoid top() {\n' + "    int a = 1;\n" * 40
    first = "```cpp\n" + long_body
    short = '```cpp\n#include "k.h"\nvoid top() {\n    int z = 0;\n'
    llm = ScriptLLM([(first, 8192), (short, 8192)])
    out = _run(tmp_path, monkeypatch, llm, max_rounds=2)
    sol = (out / "solution.cpp").read_text(encoding="utf-8")
    assert "int a = 1" in sol
    assert "int z = 0" not in sol
    assert len(sol) >= len(long_body)


def test_max_two_continues_then_no_llm(tmp_path, monkeypatch):
    chunk = '```cpp\n#include "k.h"\nvoid top() {\n    int a = 1;\n'
    llm = ScriptLLM([(chunk, 8192), (chunk, 8192), (chunk, 8192), (chunk, 8192)])
    out = _run(tmp_path, monkeypatch, llm, max_rounds=6)
    assert llm.calls == 3  # 1 initial + 2 continues
    events = [
        __import__("json").loads(ln)
        for ln in (out / "trace.jsonl").read_text().splitlines() if ln
    ]
    cont = [e for e in events if e.get("tool") == "agent" and e.get("event") == "continue"]
    assert len(cont) == 2
    stops = [e for e in events if e.get("event") == "stop" and e.get("reason") == "max_continues"]
    assert stops


def test_continue_user_clips_long_fragment_and_drops_overlong_line():
    lines = [f"    int a_{i} = 1;" for i in range(8000)]
    overlong = "9" * 250
    lines[1234] = overlong
    blob = "\n".join(lines)
    assert len(blob.splitlines()) == 8000
    user = _continue_user(blob)
    assert len(user) <= 4000
    assert overlong not in user
    assert CONTINUE_HINT in user


class SeqSelfCheck:
    def __init__(self, rcs: list[int]):
        self.rcs = list(rcs)
        self.calls = 0
        self.sources: list[str] = []

    def __call__(self, task_dir, source, top, interface, headers, timeout_s=30.0):
        self.sources.append(source)
        rc = self.rcs[self.calls] if self.calls < len(self.rcs) else -1
        self.calls += 1
        return rc, f"fake selfcheck rc={rc}\n"


def _run_checked(tmp_path, monkeypatch, llm, selfcheck, max_rounds=3):
    import agent.main as main_mod

    monkeypatch.setattr(main_mod, "HlsToolchain", lambda: FakeHls())
    monkeypatch.setattr(main_mod, "SELF_CHECK", True)
    monkeypatch.setattr(main_mod, "MAX_ROUNDS", max_rounds)
    monkeypatch.setattr(main_mod, "DEADLINE_S", 950.0)
    monkeypatch.setattr(main_mod, "self_check", selfcheck)

    task = tmp_path / "task"
    task.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    trace = Trace(str(out / "trace.jsonl"))
    try:
        solve_agent(
            llm, trace,
            prompt="Top-Level Function: `top`",
            interface="void top();",
            top="top",
            task_dir=str(task),
            output_dir=str(out),
        )
    finally:
        trace.close()
    return out


def _events(out):
    import json
    return [
        json.loads(ln)
        for ln in (out / "trace.jsonl").read_text().splitlines() if ln
    ]


def test_continue_stitch_rc_minus1_keeps_round1_compiled(tmp_path, monkeypatch):
    r1 = '#include "k.h"\nvoid top() { int compiled_r1 = 1; }\n'
    trunc = '```cpp\n#include "k.h"\nvoid top() {\n    int compiled_r1 = 1;\n'
    stitch = "```cpp\n    int stitch_bad = 2;\n}\n```\n"
    llm = ScriptLLM([("```cpp\n" + r1 + "```\n", 20), (trunc, 8192), (stitch, 40)])
    chk = SeqSelfCheck([1, -1])
    out = _run_checked(tmp_path, monkeypatch, llm, chk, max_rounds=3)
    sol = (out / "solution.cpp").read_text(encoding="utf-8")
    assert "int compiled_r1 = 1" in sol
    assert "int stitch_bad" not in sol
    assert chk.calls == 2
    keep = [e for e in _events(out) if e.get("event") == "keep_compiled"]
    assert keep and keep[-1].get("tool") == "agent"
    assert keep[-1].get("round") == 3


def test_continue_stitch_rc1_may_replace_compiled(tmp_path, monkeypatch):
    r1 = '#include "k.h"\nvoid top() { int compiled_r1 = 1; }\n'
    trunc = '```cpp\n#include "k.h"\nvoid top() {\n    int compiled_r1 = 1;\n'
    restart = '```cpp\n#include "k.h"\nvoid top() { int compiled_r3 = 3; }\n```\n'
    llm = ScriptLLM([("```cpp\n" + r1 + "```\n", 20), (trunc, 8192), (restart, 40)])
    chk = SeqSelfCheck([1, 1])
    out = _run_checked(tmp_path, monkeypatch, llm, chk, max_rounds=3)
    sol = (out / "solution.cpp").read_text(encoding="utf-8")
    assert "int compiled_r3 = 3" in sol
    assert "int compiled_r1 = 1" not in sol
    assert chk.calls == 2
    keep = [e for e in _events(out) if e.get("event") == "keep_compiled"]
    assert not any(e.get("round") == 3 for e in keep)


def test_never_compiled_longer_trunc_may_remain(tmp_path, monkeypatch):
    long_body = '#include "k.h"\nvoid top() {\n' + "    int a = 1;\n" * 40
    first = "```cpp\n" + long_body
    short = '```cpp\n#include "k.h"\nvoid top() {\n    int z = 0;\n'
    llm = ScriptLLM([(first, 8192), (short, 8192)])
    chk = SeqSelfCheck([-1, -1])
    out = _run_checked(tmp_path, monkeypatch, llm, chk, max_rounds=2)
    sol = (out / "solution.cpp").read_text(encoding="utf-8")
    assert "int a = 1" in sol
    assert "int z = 0" not in sol
    assert len(sol) >= len(long_body)
    assert chk.calls == 0
    keep = [e for e in _events(out) if e.get("event") == "keep_compiled"]
    assert not keep
