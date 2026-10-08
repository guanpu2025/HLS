#!/usr/bin/env bash
# Re-run the c2hlsc tasks whose first synthesis failed on array-type errors.
# Round 1 is expected to fail. Round 2 is the one that should use array_type.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/selftest/env.sh"
export AGENT_MAX_ROUNDS=2

tasks=(
  he_c2hlsc_aes
  he_c2hlsc_des
  he_c2hlsc_mix_columns
  he_c2hlsc_present
  he_c2hlsc_sub_bytes
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
    "he_c2hlsc_des",
    "he_c2hlsc_mix_columns",
    "he_c2hlsc_present",
    "he_c2hlsc_sub_bytes",
]
print(f"{'task':<28} {'round':<6} {'rc':<4} failure")
for name in names:
    trace = root / name / "s0" / "trace.jsonl"
    rows = [json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
    cs = [row for row in rows if row.get("tool") == "csynth"]
    if not cs:
        print(f"{name:<28} no csynth")
        continue
    for row in cs:
        print(f"{name:<28} {row.get('round')!s:<6} {row.get('rc')!s:<4} {row.get('failure')}")
PY
