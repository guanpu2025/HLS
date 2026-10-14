#!/usr/bin/env bash
# Local llama.cpp OpenAI-compatible server. Matches model/MODEL.md.
#
#   ./serve/llama.sh
#   export LLM_BACKEND=openai LLM_BASE_URL=http://127.0.0.1:8000/v1 LLM_MODEL=Coder390-Q6_K
#
# The sandbox is offline: MODEL must be a local GGUF path, not a Hub id.
set -euo pipefail

MODEL="${MODEL:-/models/Qwen3.8-27B-Coder390-Q6_K-MTP.gguf}"
PORT="${PORT:-8000}"
CTX="${CTX:-16384}"
LLAMA_SERVER="${LLAMA_SERVER:-llama-server}"

exec "$LLAMA_SERVER" \
  -m "$MODEL" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --alias Coder390-Q6_K \
  --ctx-size "$CTX" \
  --parallel 1 \
  --gpu-layers all \
  --jinja \
  --reasoning off \
  --reasoning-format deepseek
