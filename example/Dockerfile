# Build on the official base image. It carries ROCm, Vivado / Vitis and a
# working inference stack for the target architecture; rebuilding that yourself
# is a large amount of work for no score.
#
# Two variants are planned, gfx1100 (validation window, W7900) and gfx1201
# (finals, R9700). Pin the one you are targeting -- prebuilt kernels and
# wheels are not interchangeable between the two generations.
#
# ★ The tag below is a PLACEHOLDER. The real image name is announced before
#   the validation window; until then this build only works if you pass the
#   name explicitly:
#
#     docker build --build-arg BASE_IMAGE=<announced name> -t myteam-agent .
#
ARG BASE_IMAGE=fpgachina2026/base-gfx1100:REPLACE_WITH_ANNOUNCED_TAG
FROM ${BASE_IMAGE}

# --- everything must be baked in: the sandbox has no network ----------------

WORKDIR /opt/agent

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY agent/  agent/
COPY skill/  skill/
COPY serve/  serve/
COPY model/  model/
COPY run.sh run_baseline.sh manifest.json REPORT.md ./
RUN chmod +x run.sh run_baseline.sh serve/vllm.sh

# Model weights. Copy them in, or bind-mount at run time -- but they must be on
# local disk before the network goes away. `huggingface-cli download` at startup
# fails in the sandbox.
#
# COPY models/ /models/

ENV LLM_BACKEND=openai \
    LLM_BASE_URL=http://localhost:8000/v1 \
    LLM_MODEL=Qwen3-8B \
    LLM_API_KEY=dummy \
    AGENT_TMP=/tmp \
    HLS_PART=xczu3eg-sbva484-1-e \
    HLS_PERIOD_NS=5

# Do NOT set PATH for the toolchain here. The base image already exports it,
# along with XILINX_VITIS / XILINX_VIVADO / XILINX_HLS. The tools actually
# live under /tools/Xilinx/2026.1/, and the layout is version-first in 2026.1
# but tool-first in 2024.2 and earlier -- which is why CONTRACT.md section 1
# says to read the variables instead of hardcoding a path.

# Container metadata only. On Radeon Cloud both services bind 127.0.0.1 and
# just 7860 is published, via rc-tunnel. See docs/接口契约.md section 7.
EXPOSE 7860 8000

# Not an entrypoint on purpose: the organisers call run.sh / run_baseline.sh
# directly, and serve/serve_api.py is started separately on evaluation day.
CMD ["/bin/bash"]
