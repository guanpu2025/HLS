#!/usr/bin/env bash
# One agent round per c2hlsc task. Both run.sh arguments stay on one line.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/selftest/env.sh"
export AGENT_MAX_ROUNDS=1

for d in "$ROOT"/tasks/he_c2hlsc_*; do
  name="$(basename "$d")"
  echo "=== $name ==="
  "$ROOT/example/run.sh" "$d" "$ROOT/selftest/out/agent/$name/s0"
done

grep '"tool": "csynth"' "$ROOT"/selftest/out/agent/he_c2hlsc_*/s0/trace.jsonl || true
