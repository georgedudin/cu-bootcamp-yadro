# Build context is the REPO ROOT — see infra/docker-compose.yml.
#
# GPU story:
#   - Base is nvidia/cuda 12.4 + cuDNN runtime because CTranslate2
#     (faster-whisper) dlopens SYSTEM libcublas.so.12/libcudnn.so.9 at first
#     inference — the cu13 pip wheels torch ships (libcublas.so.13) do NOT
#     satisfy it (verified on the deploy box: "Library libcublas.so.12 is not
#     found"). torch keeps loading its own pip cu13 libs via RUNPATH; the two
#     coexist.
#   - The driver (libcuda) is injected at RUN time by the NVIDIA Container
#     Toolkit via the compose GPU reservation (infra/docker-compose.gpu.yml).
#   - Python 3.12 is uv-managed (base image has no python).
#   - Model weights are NOT baked in: the hf_cache volume is filled once by
#     `python -m ml.warmup` (see scripts/deploy.sh), then workers run with
#     HF_HUB_OFFLINE=1.
#   REQUIREMENT — stay 1080-friendly: ASR_COMPUTE_TYPE=int8 is the code
#   default (Pascal CC 6.1 has no float16).
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /uvx /usr/local/bin/

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    UV_PYTHON=3.12 UV_PYTHON_INSTALL_DIR=/opt/uv-python
RUN uv python install 3.12

COPY pyproject.toml uv.lock ./
COPY contracts/pyproject.toml contracts/
COPY core/pyproject.toml core/
COPY backend/pyproject.toml backend/
COPY ml/pyproject.toml ml/
RUN uv sync --frozen --package ml --no-dev --no-install-workspace

COPY contracts/ contracts/
COPY core/ core/
COPY ml/ ml/
RUN uv sync --frozen --package ml --no-dev

ENV PATH="/app/.venv/bin:$PATH"
# Queue names come from the compose `command:` (chunks | reduce)
CMD ["python", "-m", "ml.worker"]
