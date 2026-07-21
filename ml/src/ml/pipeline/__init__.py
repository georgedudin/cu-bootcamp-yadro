"""FRIEND A: this is your seam. Replace the stub with the real pipeline by
editing the import below (e.g. `from ml.pipeline.real import ...`), keeping
the exact signatures:

    transcribe_chunk(job: TranscribeChunkJob) -> ChunkResult
        ASR (faster-whisper) + diarization (pyannote) + per-turn ECAPA
        embeddings for ONE window of the canonical WAV.

    stitch(results, windows, expected_speakers, duration_s) -> StitchResult
        Global clustering of all turn embeddings -> stable speaker ids,
        teacher = most total speech time, overlap-seam dedupe.

Rules of the seam: pure functions — no DB, no Redis, no queue. Depend only on
the `contracts` package. The glue (ml/glue.py) owns all persistence.
"""

from ml.pipeline.stub import stitch, transcribe_chunk

__all__ = ["transcribe_chunk", "stitch"]
