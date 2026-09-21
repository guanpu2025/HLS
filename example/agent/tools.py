"""Vitis HLS feedback for the agent loop.

The agent only gets `csynth`. It does NOT get the official testbench -- that
stays with the organisers and is what decides L3. So the strongest signal
available inside the loop is "does the C front end accept this and can it be
scheduled", which separates L0/L1 from L4 but says nothing about correctness.

Closing that gap -- writing your own testbench, asserting invariants, checking
against a reference you derive from the task statement -- is one of the actual
design problems of this track. The example agent does not attempt it.

If Vitis HLS is not installed, every call degrades to rc=-1 with a clear reason
and the agent falls back to single-shot generation. It never pretends to have
checked something it did not.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
import textwrap

PART = os.environ.get("HLS_PART", "xczu3eg-sbva484-1-e")
PERIOD_NS = os.environ.get("HLS_PERIOD_NS", "5")


class HlsToolchain:
    """Locates the installed Vitis HLS, if any.

    `v++ -c --mode hls` runs synthesis; `vitis-run --mode hls --csim` runs C
    simulation. The agent only needs synthesis, so only v++ is looked for.
    """

    def __init__(self) -> None:
        self.exe: str | None = None
        self.reason = ""

        override = os.environ.get("VITIS_HLS_CMD", "").strip()
        if override:
            exe = shutil.which(override) or (override if os.path.isfile(override) else None)
            if exe:
                self.exe = exe
                return
            self.reason = f"VITIS_HLS_CMD={override!r} not found"
            return

        self.exe = shutil.which("v++")
        if self.exe is None:
            self.reason = (
                "no v++ on PATH; source the Vitis settings64.sh or set VITIS_HLS_CMD"
            )

    @property
    def available(self) -> bool:
        return self.exe is not None

    # ---------------------------------------------------------------- csynth

    def csynth(self, source: str, top: str, timeout_s: float = 900.0,
               headers: dict[str, str] | None = None) -> tuple[int, str]:
        """Synthesise `source` alone. Returns (rc, log excerpt).

        rc =  0  synthesis finished
        rc =  1  the tool ran and rejected the design
        rc = -1  we could not run the tool at all

        `headers` maps filename -> content and is written next to the source.
        Without it every check fails at `'foo.h' file not found`, because the
        generated code includes the header the interface told it to include and
        the scratch directory does not have one. See split_interface() in
        main.py for where the content comes from.
        """
        if not self.available:
            return -1, f"vitis hls unavailable: {self.reason}"

        work = tempfile.mkdtemp(prefix="agent_csynth_", dir=_scratch_dir())
        try:
            for name, body in (headers or {}).items():
                with open(os.path.join(work, os.path.basename(name)), "w") as fh:
                    fh.write(body)

            src = os.path.join(work, "kernel.cpp")
            with open(src, "w") as fh:
                fh.write(source)

            cmd, cwd = self._cfg_cmd(work, "kernel.cpp", top, csim=False)

            try:
                proc = subprocess.run(
                    cmd, cwd=cwd, timeout=timeout_s,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                )
                out, rc = proc.stdout, proc.returncode
            except subprocess.TimeoutExpired:
                return -1, f"csynth timed out after {timeout_s:.0f}s"

            ok = rc == 0 and _produced_rtl(work)
            return (0 if ok else 1), summarize_log(out)
        finally:
            if os.environ.get("AGENT_KEEP_WORK") != "1":
                shutil.rmtree(work, ignore_errors=True)

    def _cfg_cmd(self, work: str, src: str, top: str, csim: bool) -> tuple[list[str], str]:
        cfg = os.path.join(work, "hls.cfg")
        with open(cfg, "w") as fh:
            fh.write(
                textwrap.dedent(
                    f"""\
                    part={PART}

                    [hls]
                    flow_target=vivado
                    clock={PERIOD_NS}ns
                    syn.file={src}
                    syn.top={top}
                    """
                )
            )
        exe = self.exe or "v++"
        return [exe, "-c", "--mode", "hls", "--config", cfg, "--work_dir", work], work


# --------------------------------------------------------------------- utils

def _produced_rtl(work: str) -> bool:
    """Did synthesis actually produce something?

    Judge by artefacts, not by a log line. `v++ -c --mode hls` never prints
    "Finished C synthesis" -- that message belongs to the old `vitis_hls`
    binary, which does not exist in 2025.x / 2026.1. Keying off it makes every
    run look failed even when the RTL is sitting right there, so the repair
    loop burns all its rounds fixing code that already worked.

    Measured on 2026.1: exit code 0, zero occurrences of that string, and
    `hls/syn/report/csynth.rpt` plus `hls/syn/verilog/*.v` present. This is also
    how the organisers' judge decides L4.
    """
    return bool(
        glob.glob(os.path.join(work, "hls", "syn", "report", "*csynth*.rpt"))
        or glob.glob(os.path.join(work, "hls", "syn", "verilog", "*.v"))
        or glob.glob(os.path.join(work, "hls", "syn", "vhdl", "*.vhd"))
    )


def _scratch_dir() -> str:
    """Where csynth's working directories go.

    Node-local disk, never network storage: one csynth run creates thousands of
    small files, which is the slowest possible IO pattern on NFS. Section 9 of
    docs/API_CONTRACT.md names `/tmp/eda` and exports it as `EDA_TMP`; `AGENT_TMP`
    is what serve_api.py passes in and takes priority.

    `TRACK_TMP` is the old name of `EDA_TMP`, kept as a fallback -- the base
    image dropped the contest content in 2026-09 and renamed track -> eda.
    """
    d = (os.environ.get("AGENT_TMP")
         or os.environ.get("EDA_TMP")
         or os.environ.get("TRACK_TMP")
         or "/tmp")
    os.makedirs(d, exist_ok=True)
    return d


# Lines worth showing the model again. A full csynth log is tens of thousands of
# lines; pasting it back would crowd out the code and bury the one line that
# matters.
_KEEP = (
    "ERROR", "error:", "Compilation failed", "Unsupported", "undefined",
    "WARNING: [HLS", "Finished C synthesis", "II = ", "Latency",
)


def summarize_log(out: str, limit: int = 4000) -> str:
    """Reduce a csynth log to what the repair prompt can act on.

    Falls back to the tail when nothing matches -- an empty excerpt tells the
    model nothing, and "the tool said nothing recognisable" is itself a clue.
    """
    lines = [ln.rstrip() for ln in out.splitlines() if any(k in ln for k in _KEEP)]
    if not lines:
        lines = [ln.rstrip() for ln in out.splitlines()[-40:]]
    # Vitis repeats the same diagnostic many times; keep first occurrence only.
    text = "\n".join(dict.fromkeys(ln for ln in lines if ln))
    return text[-limit:] if len(text) > limit else text
