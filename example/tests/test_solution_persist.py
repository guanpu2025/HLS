"""solution.cpp is flushed after each candidate, before a hard kill."""

from __future__ import annotations

import json
from pathlib import Path

from agent.llm import LLMResult
from agent.main import Trace, solve_agent


CODE_R1 = '#include "k.h"\nvoid top() { int a = 1; }\n'
CODE_R2 = '#include "k.h"\nvoid top() { int a = 2; }\n'
CODE_R3 = '#include "k.h"\nvoid top() { int a = 3; }\n'


class SimulatedKill(BaseException):
    """Stand-in for SIGKILL: not caught by solve_agent."""


class FakeLLM:
    max_tokens = 8192
    temperature = 0.2

    def __init__(self, bodies: list[str], die_after: int = 2):
        self.bodies = bodies
        self.die_after = die_after
        self.calls = 0
        self.max_tokens_seen: list[int | None] = []

    def chat(self, messages, temperature=None, max_tokens=None):
        self.calls += 1
        self.max_tokens_seen.append(max_tokens)
        if self.calls > self.die_after:
            raise SimulatedKill("hard stop after round 2")
        body = self.bodies[self.calls - 1]
        text = "以下是实现：\n\n```cpp\n" + body + "```\n"
        return LLMResult(text=text, tokens_in=10, tokens_out=20)


class FakeHls:
    available = True
    exe = "/fake/v++"
    reason = ""

    def csynth(self, source, top, timeout_s=900.0, headers=None):
        return 1, "ERROR: [HLS 200-0] fake reject so the loop continues"


def test_solution_cpp_exists_after_round_2_if_hard_killed(tmp_path, monkeypatch):
    import agent.main as main_mod

    monkeypatch.setattr(main_mod, "HlsToolchain", lambda: FakeHls())
    monkeypatch.setattr(main_mod, "SELF_CHECK", False)
    monkeypatch.setattr(main_mod, "MAX_ROUNDS", 6)
    monkeypatch.setattr(main_mod, "DEADLINE_S", 950.0)

    llm = FakeLLM([CODE_R1, CODE_R2, CODE_R3], die_after=2)
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
    except SimulatedKill:
        pass
    finally:
        trace.close()

    sol = out / "solution.cpp"
    assert sol.is_file(), "solution.cpp missing after simulated hard kill"
    assert sol.read_text(encoding="utf-8") == CODE_R2
    assert llm.calls == 3  # third call is the kill; two candidates were produced


class TruncatingLLM(FakeLLM):
    def chat(self, messages, temperature=None, max_tokens=None):
        self.calls += 1
        self.max_tokens_seen.append(max_tokens)
        body = '#include "k.h"\nvoid top() { int a = 1;'
        return LLMResult(
            text="```cpp\n" + body,
            tokens_in=8000,
            tokens_out=192,
        )


def test_truncated_generation_writes_trace_and_recovers_code(tmp_path, monkeypatch):
    import agent.main as main_mod

    monkeypatch.setattr(main_mod, "HlsToolchain", lambda: FakeHls())
    monkeypatch.setattr(main_mod, "SELF_CHECK", False)
    monkeypatch.setattr(main_mod, "MAX_ROUNDS", 1)
    monkeypatch.setattr(main_mod, "LLM_CTX", 8192)

    llm = TruncatingLLM([])
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

    sol = (out / "solution.cpp").read_text(encoding="utf-8")
    assert sol.splitlines()[0] == '#include "k.h"'
    assert not any(ln.lstrip().startswith("```") for ln in sol.splitlines())

    events = [json.loads(ln) for ln in (out / "trace.jsonl").read_text().splitlines() if ln]
    trunc = [e for e in events if e.get("tool") == "extract" and e.get("event") == "truncated"]
    assert trunc, "missing extract truncated trace record"
    assert trunc[0].get("unclosed_fence") is True
    assert trunc[0].get("hit_ctx") is True


def test_finally_does_not_wipe_existing_solution_on_exception(tmp_path, monkeypatch):
    import agent.main as main_mod

    inp = tmp_path / "in"
    out = tmp_path / "out"
    inp.mkdir()
    out.mkdir()
    (inp / "prompt.txt").write_text("Top-Level Function: `top`")
    (inp / "interface.txt").write_text("void top();")
    existing = '#include "k.h"\nvoid top() { int a = 9; }\n'
    (out / "solution.cpp").write_text(existing)

    def boom(*_a, **_k):
        raise RuntimeError("mid-run exception")

    monkeypatch.setattr(main_mod, "solve_agent", boom)
    rc = main_mod.main(["--input", str(inp), "--output", str(out), "--top", "top"])
    assert rc == 0
    assert (out / "solution.cpp").read_text(encoding="utf-8") == existing


def test_finally_writes_nonempty_code(tmp_path, monkeypatch):
    import agent.main as main_mod

    inp = tmp_path / "in"
    out = tmp_path / "out"
    inp.mkdir()
    out.mkdir()
    (inp / "prompt.txt").write_text("Top-Level Function: `top`")
    (inp / "interface.txt").write_text("void top();")
    returned = '#include "k.h"\nvoid top() { int a = 4; }\n'

    monkeypatch.setattr(main_mod, "solve_agent", lambda *_a, **_k: returned)
    rc = main_mod.main(["--input", str(inp), "--output", str(out), "--top", "top"])
    assert rc == 0
    assert (out / "solution.cpp").read_text(encoding="utf-8") == returned
