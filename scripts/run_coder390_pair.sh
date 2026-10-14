#!/usr/bin/env bash
# Paired baseline.py + agent on all tasks for the Coder390 llama-server.
# Resume-friendly: skip a (mode, task) that already has a judge json.
#
#   OUT_DIR=selftest/out/coder390 scripts/run_coder390_pair.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/selftest/env.sh"

export LLM_BACKEND=openai
export LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:8081/v1}"
export LLM_API_KEY="${LLM_API_KEY:-dummy}"
export LLM_MODEL="${LLM_MODEL:-Coder390-Q6_K}"
# env.sh may already export the previous alias; this pair must hit Coder390.
if [ -z "${CODER390_KEEP_LLM_MODEL:-}" ]; then
    export LLM_MODEL=Coder390-Q6_K
fi
export LLM_TIMEOUT_S="${LLM_TIMEOUT_S:-900}"
export LLM_MAX_TOKENS=8192
export AGENT_SELF_CHECK=1
export AGENT_MAX_ROUNDS=6
export AGENT_DEADLINE_S=950
export AGENT_TMP="${AGENT_TMP:-/tmp}"

HERE="$ROOT/selftest"
TASKS_DIR="$ROOT/tasks"
AGENT_DIR="$ROOT/example"
OUT_DIR="${OUT_DIR:-$HERE/out/coder390}"
TIMEOUT="${TIMEOUT:-1800}"
PY=$(command -v python3)

mkdir -p "$OUT_DIR/results" "$OUT_DIR/logs"
TASK_LIST=$(find "$TASKS_DIR" -maxdepth 2 -name task.json -printf '%h\n' | sort)
N=$(printf '%s\n' "$TASK_LIST" | wc -l)
echo "coder390 pair  n=$N  model=$LLM_MODEL  out=$OUT_DIR  selfcheck=$AGENT_SELF_CHECK"

run_one() {
    local mode="$1" task_dir="$2"
    local tid; tid=$(basename "$task_dir")
    local dst="$OUT_DIR/$mode/$tid/s0"
    local js="$OUT_DIR/results/$mode.$tid.s0.json"
    mkdir -p "$dst"
    if [ -f "$js" ]; then
        echo "skip $mode $tid"
        return 0
    fi
    if [ ! -s "$dst/solution.cpp" ]; then
        local script=run.sh
        [ "$mode" = "baseline" ] && script=run_baseline.sh
        echo "$(date -Is)  GEN $mode $tid"
        "$AGENT_DIR/$script" "$task_dir" "$dst" >"$dst/run.log" 2>&1 || true
        [ -f "$dst/solution.cpp" ] || : > "$dst/solution.cpp"
        [ -f "$dst/trace.jsonl" ] || : > "$dst/trace.jsonl"
    else
        echo "$(date -Is)  JUDGE-ONLY $mode $tid"
    fi
    echo "$(date -Is)  JUDGE $mode $tid"
    $PY "$HERE/judge.py" \
        --task "$task_dir" \
        --solution "$dst/solution.cpp" \
        --outdir "$OUT_DIR/logs" \
        --timeout "$TIMEOUT" \
        --json "$js" || true
}

for mode in baseline agent; do
    echo
    echo "=================================================================="
    echo " $mode"
    echo "=================================================================="
    i=0
    for task_dir in $TASK_LIST; do
        i=$((i + 1))
        printf '[%s %d/%d] ' "$mode" "$i" "$N"
        run_one "$mode" "$task_dir"
    done
done

$PY "$HERE/score.py" --results "$OUT_DIR/results" --json "$OUT_DIR/score.json"
echo "done -> $OUT_DIR/score.json"
