"""Ranked keep: only a strictly better candidate replaces the retained kernel."""

from __future__ import annotations

import json

from agent.llm import LLMResult
from agent.main import Trace, solve_agent

from test_continue import ScriptLLM, SeqSelfCheck, _events


class SeqHls:
    available = True
    exe = "/fake/v++"
    reason = ""

    def __init__(self, rcs: list[int] | None = None):
        self.rcs = list(rcs) if rcs is not None else []
        self.calls = 0
        self.sources: list[str] = []

    def csynth(self, source, top, timeout_s=900.0, headers=None):
        self.sources.append(source)
        rc = self.rcs[self.calls] if self.calls < len(self.rcs) else 0
        self.calls += 1
        if rc == 0:
            return 0, "INFO: [HLS 200-0] fake csynth ok\n"
        return rc, "ERROR: [HLS 200-0] fake reject\n"


def _run_rank(tmp_path, monkeypatch, llm, selfcheck, hls, max_rounds=2):
    import agent.main as main_mod

    monkeypatch.setattr(main_mod, "HlsToolchain", lambda: hls)
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


def test_round1_csynth_keeps_same_rank_later(tmp_path, monkeypatch):
    r1 = '#include "k.h"\nvoid top() { int rank_r1 = 1; }\n'
    r2 = '#include "k.h"\nvoid top() { int rank_r2 = 2; }\n'
    llm = ScriptLLM([("```cpp\n" + r1 + "```\n", 20), ("```cpp\n" + r2 + "```\n", 20)])
    chk = SeqSelfCheck([1, 1])
    hls = SeqHls([0, 0])
    out = _run_rank(tmp_path, monkeypatch, llm, chk, hls, max_rounds=2)
    sol = (out / "solution.cpp").read_text(encoding="utf-8")
    assert "int rank_r1 = 1" in sol
    assert "int rank_r2" not in sol
    assert hls.calls >= 1
    assert "int rank_r1 = 1" in hls.sources[0]
    keep = [e for e in _events(out) if e.get("event") == "keep_better"]
    assert keep and keep[-1].get("old_rank") == 2 and keep[-1].get("new_rank") == 2
    assert keep[-1].get("round") == 2
    assert not any(e.get("event") == "skip_csynth" and e.get("round") == 1 for e in _events(out))


def test_rank3_may_replace_rank2(tmp_path, monkeypatch):
    r1 = '#include "k.h"\nvoid top() { int rank_r1 = 1; }\n'
    r2 = '#include "k.h"\nvoid top() { int rank_r2 = 2; }\n'
    llm = ScriptLLM([("```cpp\n" + r1 + "```\n", 20), ("```cpp\n" + r2 + "```\n", 20)])
    chk = SeqSelfCheck([1, 0])
    hls = SeqHls([0, 0])
    out = _run_rank(tmp_path, monkeypatch, llm, chk, hls, max_rounds=2)
    sol = (out / "solution.cpp").read_text(encoding="utf-8")
    assert "int rank_r2 = 2" in sol
    assert "int rank_r1 = 1" not in sol
    acc = [e for e in _events(out) if e.get("event") == "accept"]
    assert acc and acc[-1].get("round") == 2


def test_selfcheck_minus1_csynth_ok_does_not_end_or_lose(tmp_path, monkeypatch):
    r1 = '#include "k.h"\nvoid top() { int rank_r1 = 1; }\n'
    r2 = '#include "k.h"\nvoid top() { int rank_r2 = 2; }\n'
    llm = ScriptLLM([("```cpp\n" + r1 + "```\n", 20), ("```cpp\n" + r2 + "```\n", 20)])
    chk = SeqSelfCheck([-1, -1])
    hls = SeqHls([0, 0])
    out = _run_rank(tmp_path, monkeypatch, llm, chk, hls, max_rounds=2)
    sol = (out / "solution.cpp").read_text(encoding="utf-8")
    assert "int rank_r1 = 1" in sol
    assert "int rank_r2" not in sol
    assert llm.calls == 2
    assert hls.calls == 2
    acc = [e for e in _events(out) if e.get("event") == "accept"]
    assert not acc
    keep = [e for e in _events(out) if e.get("event") == "keep_better"]
    assert keep and keep[-1].get("round") == 2
    assert keep[-1].get("old_rank") == 2 and keep[-1].get("new_rank") == 2
