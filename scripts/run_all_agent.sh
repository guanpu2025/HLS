#!/usr/bin/env bash
# Two agent rounds for every task. No baseline and no L0-L4 judge.
# Writes selftest/out/agent/<task>/s0/trace.jsonl and a one-line summary.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/selftest/env.sh"
export AGENT_MAX_ROUNDS=2

SUMMARY="$ROOT/selftest/out/agent_failures.tsv"
mkdir -p "$ROOT/selftest/out"
printf 'task\tround\trc\tfailure\n' > "$SUMMARY"

for cfg in "$ROOT"/tasks/*/task.json; do
  d="$(dirname "$cfg")"
  name="$(basename "$d")"
  echo "=== $name ==="
  "$ROOT/example/run.sh" "$d" "$ROOT/selftest/out/agent/$name/s0"
  python3 - "$ROOT/selftest/out/agent/$name/s0/trace.jsonl" "$name" >> "$SUMMARY" <<'PY'
import json, sys
path, name = sys.argv[1], sys.argv[2]
rows = [json.loads(line) for line in open(path) if line.strip()]
cs = [row for row in rows if row.get("tool") == "csynth"]
if not cs:
    err = next((row.get("excerpt", "")[:120] for row in rows if row.get("event") == "error"), "no csynth")
    print(f"{name}\t-\t-\t{err}")
else:
    for row in cs:
        print(f"{name}\t{row.get('round')}\t{row.get('rc')}\t{row.get('failure')}")
PY
done

echo "summary -> $SUMMARY"
