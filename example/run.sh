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

# Official eval calls only `./run.sh <in> <out>` and does not source env.sh.
# Unset variables fall back to the submission defaults that match MODEL.md
# and the measured Coder390 pair. Already-set values (sandbox LLM_BASE_URL,
# per-task AGENT_DEADLINE_S) are left alone.
export LLM_BACKEND="${LLM_BACKEND:-openai}"
export LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export LLM_MODEL="${LLM_MODEL:-Coder390-Q6_K}"
export LLM_API_KEY="${LLM_API_KEY:-dummy}"
export LLM_MAX_TOKENS="${LLM_MAX_TOKENS:-8192}"
export LLM_TIMEOUT_S="${LLM_TIMEOUT_S:-900}"
export AGENT_SELF_CHECK="${AGENT_SELF_CHECK:-1}"
export AGENT_MAX_ROUNDS="${AGENT_MAX_ROUNDS:-6}"
export AGENT_DEADLINE_S="${AGENT_DEADLINE_S:-950}"

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
