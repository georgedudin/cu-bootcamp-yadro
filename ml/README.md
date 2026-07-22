# ml/ — Friend A's lane

You implement **two pure functions**. Everything else in `ml/` (worker, DB, queue,
retries) is George's glue and already works end-to-end with a stub.

## Your seam

`src/ml/pipeline/__init__.py` currently does:

```python
from ml.pipeline.stub import stitch, transcribe_chunk
```

Create `src/ml/pipeline/real.py` with the same two signatures and flip that one
import. That's the whole integration. Rules of the seam:

- **Pure functions** — no DB, no Redis, no queue, no global state you can't rebuild.
- Depend only on the `contracts` package (and your ML libs).
- The glue (`src/ml/glue.py`) owns all persistence, the barrier, and retries.

## The two functions

```python
def transcribe_chunk(job: TranscribeChunkJob) -> ChunkResult:
    """ASR (faster-whisper) + diarization (pyannote) + per-turn ECAPA
    embeddings for ONE window of the canonical 16 kHz WAV.
    Read job.wav_uri, process [job.start_s, job.end_s] (absolute seconds)."""

def stitch(
    results: list[ChunkResult],
    windows: list[ChunkWindow],
    expected_speakers: int | None,
    duration_s: float,
) -> StitchResult:
    """Global clustering of all turn embeddings -> stable speaker ids
    ('teacher', 'student_1', ...). Teacher = most total speech time.
    Dedupe the ~5 s overlap seams using `windows`.
    If expected_speakers is set, cluster to exactly that many (incl. teacher)."""
```

## Types (defined in `contracts/src/contracts/jobs.py`)

| Type | Shape | Notes |
|------|-------|-------|
| `TranscribeChunkJob` | `recording_id, chunk_index, wav_uri, start_s, end_s, target_sr, expected_speakers?` | one window of the WAV |
| `ChunkResult` | `recording_id, chunk_index, segments[], turns[]` | your map-step output |
| `ChunkSegment` | `start, end, text, local_speaker, words[]` | `local_speaker` is **chunk-LOCAL** (`SPEAKER_00`…) — meaningless across chunks |
| `Turn` | `start, end, local_speaker, embedding` | embedding = **exactly 192 floats** (ECAPA; pydantic-enforced `EMBEDDING_DIM`) |
| `ChunkWindow` | `chunk_index, start_s, end_s` | chunk boundaries, for seam dedupe |
| `StitchResult` | `speakers: StitchSpeaker[], segments: TimelineSegment[]` | your reduce-step output |
| `StitchSpeaker` | `id, role, total_s, turn_count` | `id` ∈ `teacher`, `student_N`; `role` ∈ `teacher`/`student` |
| `TimelineSegment` | `start, end, speaker_id, text` | the final timeline |

All timestamps are absolute seconds within the recording. `expected_speakers`
**includes the teacher** (12 students + 1 teacher → 13).

## How your code gets called

```
backend enqueues → Redis queue "chunks" ─→ worker.py (RQ SimpleWorker)
                                            └→ glue.transcribe_chunk(payload)
                                                └→ YOUR transcribe_chunk(job)   # pure
                                                glue upserts result + atomic barrier
                        last chunk done ─→ Redis queue "reduce"
                                            └→ glue.stitch_recording(payload)
                                                └→ YOUR stitch(...)             # pure
                                                glue writes speakers+segments, status=done
```

`SimpleWorker` (no fork) is deliberate: CUDA can't re-init in a forked child and
your models stay warm between jobs. Failures/retries are glue's problem — just
raise; after the final retry the recording is marked `failed`.

## Invariants your `stitch` must keep

`tests/test_stub_pipeline.py` encodes them (they run against the stub today and
must pass against `real.py` — keep tests deterministic, no randomness):

- **Identity survives label flips** — chunk-local labels (`SPEAKER_00`/`01`) may be
  swapped arbitrarily between chunks; global ids must stay stable via embeddings.
- **Seam dedupe** — identical segments duplicated in the chunk overlap are emitted once.

## Dependencies & local loop

Add your ML deps to `ml/pyproject.toml` **only** (never `contracts`/`core` — the
backend image must stay lightweight): `faster-whisper`, `pyannote.audio`,
`speechbrain`, `scikit-learn`, `torch`. Then from the **repo root**: `uv lock`.

```bash
make test   # pytest incl. ml/tests (venv auto-managed outside the repo)
make up     # full stack in docker; workers: ml-chunk-worker, ml-reduce-worker
```

## GPU / Docker

Follow the numbered `FRIEND A` comment in `infra/dockerfiles/ml.Dockerfile`
(CUDA 12 + cuDNN 9 base, bake the gated pyannote weights with your HF token,
run with `HF_HUB_OFFLINE=1`) and uncomment the GPU blocks in
`infra/docker-compose.yml` (grep `FRIEND A`).

**Hard requirement: stay 1080-friendly.** `ASR_COMPUTE_TYPE=int8` is the default
everywhere (Pascal CC 6.1 can't run float16 — CTranslate2 needs CC ≥ 7.0). The
bootcamp box (RTX A4000) can opt into float16 via `infra/.env` — never in code.

## Read more

`docs/architecture.md`: §4.2 map step · §4.3 reduce/stitch · §5B the wire
contract · §7.2 worker model · §10 resolved defaults (chunk 45 s / 5 s overlap,
model choices, thresholds).
