"""One-shot model warmup gate. Run via `docker compose run --rm ml-warmup`.

scripts/deploy.sh runs this between `build` and `up`: offline first (a warm
/hf cache passes in ~a minute with no token use), then online as fallback
(cold cache downloads with HF_TOKEN from the server's infra/.env). Exit 0 =
models load on this machine's device; exit 1 = the deploy must abort BEFORE
the old, working workers are replaced.
"""

import logging
import os
import sys
import time


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    log = logging.getLogger("ml.warmup")
    log.info(
        "warmup: HF_HOME=%s offline=%s token=%s device=%s asr=%s/%s diarization=%s",
        os.getenv("HF_HOME"),
        os.getenv("HF_HUB_OFFLINE", "0"),
        "set" if (os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")) else "MISSING",
        os.getenv("ML_DEVICE", "auto"),
        os.getenv("ASR_MODEL", "large-v3"),
        os.getenv("ASR_COMPUTE_TYPE", "int8"),
        os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1"),
    )
    started = time.monotonic()
    try:
        from ml.pipeline import preload_chunk_models  # heavy imports stay lazy

        preload_chunk_models()
    except Exception:
        log.exception("warmup FAILED after %.0fs", time.monotonic() - started)
        return 1
    log.info("warmup OK in %.0fs", time.monotonic() - started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
