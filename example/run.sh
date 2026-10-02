#!/usr/bin/env bash
# run.sh <input_dir> <output_dir>
#
#   <input_dir>/prompt.txt      task statement
#   <input_dir>/interface.txt   top-level signature and type definitions
#
#   <output_dir>/solution.cpp   generated HLS C++ (empty file if we failed)
#   <output_dir>/trace.jsonl    one JSON object per tool / model call
#
# The contract is: never fail loudly. "Could not solve it" and "the service is
# broken" must stay distinguishable at the protocol level, so a failed run still
# produces an empty solution.cpp and exits 0.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IN="${1:?usage: run.sh <input_dir> <output_dir>}"
OUT="${2:?usage: run.sh <input_dir> <output_dir>}"

mkdir -p "$OUT"

cd "$HERE"
python3 -m agent.main --input "$IN" --output "$OUT"
rc=$?

# Safety net: the harness expects these two files to exist no matter what.
[ -f "$OUT/solution.cpp" ] || : > "$OUT/solution.cpp"
[ -f "$OUT/trace.jsonl" ]  || : > "$OUT/trace.jsonl"

if [ $rc -ne 0 ]; then
    echo "run.sh: agent exited with $rc, emitted empty solution" >&2
fi
exit 0
