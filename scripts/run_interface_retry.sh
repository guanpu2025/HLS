#!/usr/bin/env bash
# Tasks whose last csynth in the full sweep was failure=interface.
# Three rounds so aes/sub_bytes, which become interface on round 2, inject
# hls-interface-contract on round 3.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/selftest/env.sh"
# EVO generates slower than the W7900. 950s is a conservative stand-in for a
# 360s contest budget on generation-bound tasks. env.sh stays at 360.
export AGENT_DEADLINE_S=950
export AGENT_MAX_ROUNDS=3

tasks=(
  he_c2hlsc_aes
  he_c2hlsc_sub_bytes
  he_machsuite_kmp_kmp
  he_machsuite_stencil_stencil3d
  he_polybench_2mm
  he_polybench_3mm
  he_polybench_fixed_2mm
  he_polybench_fixed_3mm
)

for name in "${tasks[@]}"; do
  echo "=== $name ==="
  "$ROOT/example/run.sh" \
    "$ROOT/tasks/$name" \
    "$ROOT/selftest/out/agent/$name/s0"
done

python3 - "$ROOT" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]) / "selftest/out/agent"
names = [
    "he_c2hlsc_aes",
    "he_c2hlsc_sub_bytes",
    "he_machsuite_kmp_kmp",
    "he_machsuite_stencil_stencil3d",
    "he_polybench_2mm",
    "he_polybench_3mm",
    "he_polybench_fixed_2mm",
    "he_polybench_fixed_3mm",
]
print(f"{'task':<32} {'round':<6} {'rc':<4} failure")
for name in names:
    trace = root / name / "s0" / "trace.jsonl"
    rows = [json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
    injected = [row.get("selected") for row in rows if row.get("event") == "inject"]
    cs = [row for row in rows if row.get("tool") == "csynth"]
    if not cs:
        print(f"{name:<32} no csynth  injected={injected}")
        continue
    for row in cs:
        print(f"{name:<32} {row.get('round')!s:<6} {row.get('rc')!s:<4} {row.get('failure')}")
    print(f"{'':<32} injected {injected}")
PY
