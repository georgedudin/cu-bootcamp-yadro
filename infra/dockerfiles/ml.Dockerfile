# Build context is the REPO ROOT — see infra/docker-compose.yml.
#
# GPU story (no CUDA base image on purpose):
#   - torch on linux resolves from uv.lock as the cu13 PyPI build, which ships
#     the complete CUDA runtime as pip `nvidia-*` wheels — a nvidia/cuda base
#     would add a SECOND, unused runtime.
#   - The driver (libcuda) is injected at RUN time by the NVIDIA Container
#     Toolkit via the compose GPU reservation (infra/docker-compose.gpu.yml).
#   - CTranslate2 (faster-whisper) dlopens cuDNN/cuBLAS — LD_LIBRARY_PATH
#     below points it at the pip wheels.
#   - Model weights are NOT baked in: the hf_cache volume is filled once by
#     `python -m ml.warmup` (see scripts/deploy.sh), then workers run with
#     HF_HUB_OFFLINE=1.
#   REQUIREMENT — stay 1080-friendly: ASR_COMPUTE_TYPE=int8 is the code
#   default (Pascal CC 6.1 has no float16). Caveat: the cu13 wheel stack
#   itself has dropped Pascal — an actual GTX 1080 box would need a cu12
#   torch lock in addition to int8.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /uvx /usr/local/bin/

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

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
ENV NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility
# CTranslate2 dlopens cuDNN/cuBLAS from the pip-provided nvidia wheels
ENV LD_LIBRARY_PATH=/app/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib:/app/.venv/lib/python3.12/site-packages/nvidia/cublas/lib
# Queue names come from the compose `command:` (chunks | reduce)
CMD ["python", "-m", "ml.worker"]
