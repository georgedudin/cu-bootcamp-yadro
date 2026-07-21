# Build context is the REPO ROOT — see infra/docker-compose.yml.
#
# FRIEND A — GPU version of this image:
#   1. Switch the base to a CUDA 12 / cuDNN 9 image (faster-whisper's
#      CTranslate2 needs both), e.g. nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
#      + install python3.12, or a pytorch/pytorch:*-cuda12* image.
#   2. Add your deps to ml/pyproject.toml (faster-whisper, pyannote.audio,
#      speechbrain, scikit-learn) and `uv lock` from the repo root.
#   3. Bake the gated pyannote weights offline: download once with your HF
#      token, COPY the HF cache in, set HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1.
#   4. Uncomment the GPU reservation in docker-compose.yml.
#   REQUIREMENT — stay 1080-friendly (Pascal, compute capability 6.1):
#   CTranslate2 float16 needs CC >= 7.0, so ASR_COMPUTE_TYPE=int8 is the
#   default (supported on 6.1). The current bootcamp box (RTX A4000, CC 8.6)
#   also runs float16 — opt in via infra/.env there, never in code defaults.
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
# Queue names come from the compose `command:` (chunks | reduce)
CMD ["python", "-m", "ml.worker"]
