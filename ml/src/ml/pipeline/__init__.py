"""The ML seam (Friend A's domain). Pure functions — no DB, no Redis, no
queue; depend only on the `contracts` package. The glue (ml/glue.py) owns all
persistence.

    transcribe_chunk(job: TranscribeChunkJob) -> ChunkResult
        ASR (faster-whisper) + diarization (pyannote) + per-turn ECAPA
        embeddings for ONE window of the canonical WAV.

    stitch(results, windows, expected_speakers, duration_s) -> StitchResult
        Global clustering of all turn embeddings -> stable speaker ids,
        teacher = most total speech time, overlap-seam dedupe.

    preload_chunk_models()
        Eagerly load the chunk models (worker boot / deploy warmup) so a
        broken model stack fails fast instead of churning job retries.
"""

from ml.pipeline.engine import preload_chunk_models, stitch, transcribe_chunk

__all__ = ["transcribe_chunk", "stitch", "preload_chunk_models"]
