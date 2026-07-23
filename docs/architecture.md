# Architecture — Local ASR + Diarization service for EdTech analytics (YADRO)

> Tech-scoping / architecture document. Companion to [`task.md`](./task.md).
> **Audience:** the 3-person team building this. This doc is the **contract**: read it and you
> can start your part without waiting on anyone else.
>
> **Status:** v1, pre-implementation. Library facts are verified from primary sources
> (see [References](#references-primary-sources)); a few numbers (thresholds, chunk length) are
> starting defaults to be tuned during build.

## 1. Context & team split

We build a fully-**local / on-prem** service that transcribes lecture audio (faster-whisper) and
separates speakers (diarization), **keeping each speaker's ID stable across the entire recording**
even though audio is processed in 30–60 s chunks. See [`task.md`](./task.md) for the graded DoD.

Three people build in parallel:

| Owner | Area | Responsible for |
|-------|------|-----------------|
| **George** | Backend / orchestration / infra | FastAPI API, job orchestration, Postgres, blob storage, `docker-compose`, the contracts |
| **Friend A** | ML | The worker pipeline: ASR, diarization, embeddings, cross-chunk clustering |
| **Friend B** | Frontend | React (Vite) SPA: upload, file list + status, the dynamic colored timeline player |

**The core design goal of this document is to let those three streams proceed independently.**
The way we achieve that is a **locked interaction protocol** (§5) plus a **stub ML worker** and
**fixtures** (built next round) so the frontend and backend can be developed end-to-end before the
real ML exists. If the seams in §5 are right, nobody blocks anybody.

## 2. Definition of Done → architecture mapping

| Tier | Requirement (from task.md) | Delivered by |
|------|----------------------------|--------------|
| **Satisfactory** | Accepts audio, chunks it, transcribes via faster-whisper **without OOM**; binary teacher/students split; demo timeline | streaming chunker (§4) + per-chunk ASR jobs + 2-class assignment + FE timeline (§5A) |
| **Good** | Several speakers, IDs **mostly** stable across chunks | per-turn ECAPA embeddings + global clustering in the reduce step (§4, §4.3) |
| **Excellent** | **Exact** count (N students + 1 teacher); a specific student's ID stable the whole lecture | clustering + optional **`expected_speakers` hint** + teacher heuristic (§4.3) |

The **Excellent** tier is the highest grade-risk item, and it is mostly an **ML-tuning** problem
(clustering thresholds on short classroom utterances), **not** an architecture problem — see
[Risks §9.1](#91-exact-speaker-count-is-the-riskiest-requirement). The architecture makes the
Excellent tier *reachable* (embeddings + global clustering + optional count hint); hitting it is
Friend A's tuning work.

## 3. System topology

Monorepo, containerized, single-box `docker-compose` for on-prem deployment.

```
┌───────────┐   REST / JSON    ┌──────────────────────────┐   enqueue    ┌──────────┐
│ Frontend  │ ───────────────► │  Backend (FastAPI)       │ ───────────► │  Redis   │  transport
│ React /   │ ◄─────────────── │  • REST API for the FE   │              │  (queue) │   only
│ Vite      │   poll 2–3 s     │  • job orchestrator      │ ◄─────────── └────┬─────┘
└─────┬─────┘                  │  • owns Postgres + blobs │  results         │ consume
      │ audio stream (Range)   └───────────┬──────────────┘                  ▼
      └─────────────────────────────────────┤                        ┌──────────────┐
                                             ▼                        │  ML workers  │
                                       ┌──────────┐   blob volume     │  ASR + diar  │
                                       │ Postgres │   (mp3 + wav)      │  + embed +   │
                                       │  (SoT)   │                    │  stitch (GPU)│
                                       └──────────┘                    └──────────────┘
```

**Responsibilities:**
- **Backend** owns everything stateful: the REST API, Postgres (the **source of truth**), the blob
  volume (audio), and it is the only producer onto the queue.
- **Redis** is **transport only** — it moves jobs. It is not the source of truth (a broker is not a
  database). Job state lives in Postgres so the frontend can poll it and so nothing is lost on a
  Redis restart.
- **ML workers** consume jobs, run the GPU pipeline, and write results back to Postgres/blob.

## 4. Processing pipeline — a map/reduce over chunks

```
 upload ──► INGEST ──► [ chunk 0 job ] ─┐
 (backend)  (backend)  [ chunk 1 job ]  ├─► (all done, atomic barrier) ─► STITCH ─► serve
                       [ chunk N job ] ─┘        (reduce, one job)       (backend)
                        MAP (ML workers, parallel)
```

### 4.1 Ingest (backend, synchronous on upload)

1. Stream the uploaded mp3 to the blob volume (never fully in memory — `UploadFile` spools to disk).
2. Create the `recording` row (`status = uploaded`).
3. **Decode once** with `ffmpeg` → a canonical **16 kHz mono WAV**, stored alongside the mp3. All
   downstream workers read the WAV; the mp3 is kept **only for playback**. This avoids re-decoding
   mp3 in every chunk job and guarantees a consistent sample rate for ASR + embeddings.
4. Compute duration; create N `chunk` rows for **45 s windows with 5 s overlap** (defaults —
   configurable; see [§10](#10-resolved-defaults)); set `chunks_remaining = N`; enqueue one
   `transcribe_chunk` job per chunk; set `status = queued`.

Why chunk on the backend rather than in the worker: the backend owns the canonical WAV and the
job/state model, so it decides the windows and creates the trackable `chunk` rows the frontend
polls. Workers stay stateless — they receive `(wav_uri, start_s, end_s)` and do the ML.

### 4.2 Map — one job per chunk (ML worker)

For each `transcribe_chunk` job, the worker:
1. Reads its window from the canonical WAV (by byte offset — memory-bounded, ~one window in RAM).
2. **ASR** (faster-whisper) → text segments with timestamps, offset to absolute recording time.
3. **Diarization** (pyannote) → local speaker **turns** (chunk-local labels like `SPEAKER_00`).
4. **Embedding** per turn (speechbrain ECAPA, 192-dim).
5. **Upserts** the chunk result keyed by `(recording_id, chunk_index)` (idempotent — a retry
   overwrites cleanly), then triggers the **atomic barrier** ([§7.3](#73-the-all-chunks-done-barrier-atomic)).

Chunk-local speaker labels are meaningless across chunks (chunk 3's `SPEAKER_00` ≠ chunk 7's
`SPEAKER_00`). Making them consistent is the reduce step's whole job.

### 4.3 Reduce / stitch — one job when all chunks are done

Fired exactly once by the atomic barrier. The worker:
1. Loads **every** turn embedding across all chunks.
2. **Global clustering** → stable global speaker IDs (this is what persists identity across
   chunks): agglomerative clustering, **cosine distance + `average` linkage**.
   - If `expected_speakers` was supplied → cluster to exactly that many (`n_clusters`).
   - Else → `distance_threshold` (≈ 0.65–0.8, tuned on a labeled lecture hour).
   - Average multiple turns per local speaker before clustering for stability.
3. **Teacher heuristic:** the global speaker with the **most total speech time** is labeled
   `teacher` (lectures are teacher-dominated); the rest are `student_1..student_k`. (Assumption;
   overridable later if we add a UI to correct it.)
4. **Dedupe the overlap regions** between adjacent chunks (each 5 s seam is transcribed/diarized
   twice) and **merge** a turn's two partial embeddings when it straddles a boundary.
5. Assign a global `speaker_id` to each ASR segment by **maximum time-overlap** with the global
   speaker turns.
6. Write `speakers` + final `segments`; set `status = done`.

### 4.4 GPU reality check (sets throughput expectations)

We target **GPU-guaranteed** deployment. With **one GPU**, the GPU is the throughput bottleneck and
map "parallelism" is really *pipeline throughput on one device*. So `chunk = job` earns its keep
less through raw parallelism and more through **progress granularity** (done/total for the FE),
**retry isolation** (one bad chunk doesn't redo the whole lecture), and **memory-bounding**. With
**multiple GPUs**, chunk jobs give true parallelism (one worker pinned per GPU). The design is
identical either way; this only sets expectations for how fast a 2-hour lecture finishes.

### 4.5 ML stack (Friend A's domain — this doc fixes the *contract*, not the internals)

Verified from primary sources; Friend A owns the final choices. GPU baseline:

| Stage | Recommended | Notes |
|-------|-------------|-------|
| ASR | **faster-whisper `large-v3`**, `float16`, CUDA | Accepts the 16 kHz WAV window; `word_timestamps=True` for word-level timing |
| Diarization (per chunk) | **pyannote `speaker-diarization-community-1`** (or `3.1`) | **Gated** on HF (token + accept conditions). Emits turns with times, **not** embeddings |
| Embedding (per turn) | **speechbrain `spkrec-ecapa-voxceleb`** | ECAPA-TDNN, **192-dim, NOT gated**, offline, GPU. Picked over `pyannote/embedding` (gated) to keep gating to one model |
| Clustering (reduce) | agglomerative, cosine + `average` linkage | `n_clusters` if count known, else `distance_threshold` |

- **Worth benchmarking:** **NeMo Sortformer** — GPU-native *streaming* diarization with automatic
  speaker counting and cross-segment permutation handling; could simplify the map+reduce split.
- **Rejected:** **WhisperX** — loads the whole file into memory, which breaks the chunked /
  memory-bounded requirement (the entire reason this problem is hard).

## 5. Interaction protocol — THE LOCK

This is the part that lets three people build at once. Both wire contracts become the single
source of truth in a shared **`contracts/`** package (next round): Pydantic models imported by
**backend + ml**, JSON Schema exported → **TypeScript** types generated for the **frontend**.
Shipped with **fixtures** + a **stub ML worker** so FE/BE build against fakes first.

### 5A. Frontend ↔ Backend (REST / JSON)

| Method & path | Purpose | Response |
|---------------|---------|----------|
| `POST /api/recordings` | Upload mp3 (≤ 200 MB, streamed to disk). Optional form field `expected_speakers: int` | `{ id, status }` |
| `GET /api/recordings` | List all recordings | `[{ id, filename, uploaded_at, duration_s, status, progress }]` |
| `GET /api/recordings/{id}` | One recording's detail + status | recording object |
| `GET /api/recordings/{id}/timeline` | The render payload for the player | timeline object (below) |
| `GET /api/recordings/{id}/audio` | Stream the mp3 for the `<audio>` player | `FileResponse` — native HTTP **Range** support, so seeking works out of the box |

**Status updates: polling.** The frontend polls `GET /api/recordings/{id}` every **2–3 s** until
the status is terminal. Chosen over SSE/WebSocket for on-prem simplicity and proxy-friendliness;
revisit only if sub-second latency is ever needed.

**Status state machine:**
```
uploaded ──► queued ──► processing ──► stitching ──► done
                            │                          
                            └──────────► failed  (any stage, after retries)
```
`progress = { done_chunks, total_chunks }`.

**Upload semantics of `expected_speakers`:** the **total** number of distinct speakers expected,
**including the teacher** (e.g. a class of 12 students + 1 teacher → `13`). When present, the
reduce step clusters to exactly this many speakers — the pragmatic path to the "exact count"
(Excellent) tier. Optional; omit it and the system estimates the count itself.

**Timeline payload (drives the colored player):**
```jsonc
{
  "recording_id": "…",
  "duration_s": 3600.0,
  "speakers": [
    { "id": "teacher",   "role": "teacher", "total_s": 2100.0 },
    { "id": "student_1", "role": "student", "total_s":  240.0 },
    { "id": "student_2", "role": "student", "total_s":  180.0 }
  ],
  "segments": [
    { "start": 0.0,  "end": 12.4, "speaker_id": "teacher",   "text": "Good morning…" },
    { "start": 13.0, "end": 15.2, "speaker_id": "student_1", "text": "Here." }
    // Gaps between segments = silence. The backend emits NO explicit silence rows.
  ]
}
```

**Frontend rendering rules (Friend B):**
- **Silence = the gaps** between consecutive segments → paint **gray**. The backend deliberately
  does not emit `speaker_id: null` rows (smaller payload, simpler backend) — the FE infers gaps.
- `role == "teacher"` → **red**.
- Each `student_N` → a **distinct, slightly dimmed** color from a palette. **The frontend owns the
  palette**; the backend owns only the **stable ids + roles**. Same `student_1` across the whole
  timeline = the same color, because the id is stable (that's the point of the reduce step).

### 5B. Backend ↔ ML (job + result contract)

Two job types on the queue, and one result shape written back to Postgres.

**Job `transcribe_chunk`** (map — backend → worker):
```jsonc
{ "recording_id": "…", "chunk_index": 3, "wav_uri": "…/rec.wav",
  "start_s": 135.0, "end_s": 185.0, "target_sr": 16000, "expected_speakers": 13 /* optional */ }
```

**Chunk result** (worker upserts to Postgres, keyed by `(recording_id, chunk_index)`):
```jsonc
{ "recording_id": "…", "chunk_index": 3,
  "segments": [ { "start": 137.1, "end": 140.0, "text": "…", "local_speaker": "SPEAKER_00",
                  "words": [ { "start": 137.1, "end": 137.4, "word": "So" } ] } ],
  "turns":    [ { "start": 137.0, "end": 141.2, "local_speaker": "SPEAKER_00",
                  "embedding": [ /* float32 × 192 */ ] } ] }
```

**Job `stitch_recording`** (reduce — enqueued by the barrier):
```jsonc
{ "recording_id": "…" }
```
Reads all chunk results for the recording → writes `speakers` + final `segments` → `status = done`.

## 6. Data model (Postgres — the source of truth)

Redis moves jobs; **Postgres holds truth** (status, results, everything the frontend reads).

```
recordings ──1:N──► chunks          (map results: segments + turn embeddings)
     │
     ├────────1:N──► speakers        (reduce output: id, role, totals)
     └────────1:N──► segments        (reduce output: the final timeline the FE queries)
```

| Table | Key columns |
|-------|-------------|
| `recordings` | `id, filename, uploaded_at, duration_s, status, expected_speakers?, chunks_total, chunks_remaining, mp3_uri, wav_uri` |
| `chunks` | `id, recording_id, chunk_index, start_s, end_s, status, retry_count, result_jsonb` — `UNIQUE(recording_id, chunk_index)` |
| `speakers` | `id, recording_id, speaker_id, role, total_speech_s, turn_count` |
| `segments` | `id, recording_id, start_s, end_s, speaker_id, text` — indexed on `(recording_id, start_s)` |

**Idempotency:** chunk writes upsert on `(recording_id, chunk_index)`; the reduce step is a pure
function of the `chunks` rows, so re-running it is safe. `chunks_remaining` drives the barrier (§7.3).
SQLAlchemy 2.x + Alembic migrations.

## 7. Orchestration (George's domain — extra rigor)

### 7.1 Queue choice: **RQ (Redis Queue) + Postgres as source of truth**

Chosen over Celery / arq / Dramatiq for a 3-person on-prem team: minimal operational weight, sync
workers fit blocking ML cleanly, actively maintained (v2.10, Jun 2026). **Alternative:** Celery if
we later want native `chord` barriers + prefork-warm models — the cost is more operational weight
and chord-over-Redis edge cases. **Rejected:** arq (async-only — poor fit for blocking GPU work),
Dramatiq (threading/GIL concerns for CPU-bound Python, no built-in job state).

### 7.2 GPU worker model (two corrections to the naive setup)

1. **Size the worker pool to GPU capacity** — roughly **one chunk-worker per GPU**. Do **not** run
   several worker replicas fighting over one device's VRAM (each loads `large-v3` + pyannote).
2. **Use RQ `SimpleWorker`, not the default forking worker.** CUDA cannot be re-initialized in a
   forked child process ("Cannot re-initialize CUDA in forked subprocess"). `SimpleWorker` runs the
   job in-process, so the model is **loaded once at worker start and stays warm** across jobs. (The
   same "no fork after CUDA init" gotcha applies to Celery → use `--pool=solo` / post-fork init.)

The `stitch_recording` reduce job is CPU/GPU-light (clustering embeddings) — it can run on a small
separate `ml-reduce-worker` so a long map queue never starves stitching.

### 7.3 The all-chunks-done barrier (atomic)

The reduce step must run **exactly once**, after the last chunk. A naive `SELECT COUNT(*) …` then
"if zero, enqueue" has a **race**: under concurrent workers it can enqueue reduce twice or never.
Do it in one atomic statement:

```sql
UPDATE recordings
   SET chunks_remaining = chunks_remaining - 1
 WHERE id = :recording_id
RETURNING chunks_remaining;
-- The worker that observes 0 (and only that worker) enqueues stitch_recording.
```

(Equivalent: `SELECT … FOR UPDATE`.) The invariant: **decrement-and-read is atomic**, so exactly
one worker sees `0`. Never check-then-act without a row lock.

### 7.4 Retries, idempotency, failure policy

- Chunk jobs **retry with backoff**; writes are **idempotent** (upsert by `(recording_id,
  chunk_index)`), so a retried or crashed-then-rerun chunk is safe.
- A chunk that still fails after max retries → `recording.status = failed`, with the failing chunk
  recorded. **v1 hard-fails** the recording; emitting a best-effort partial timeline is a v2 option.
- The reduce step is idempotent (recomputes from chunk rows), so it too is safe to retry.

## 8. Infrastructure

- **`docker-compose` services:** `frontend`, `backend`, `redis` (AOF persistence on), `postgres`,
  `ml-chunk-worker` (GPU, `SimpleWorker`, pool sized to GPUs), `ml-reduce-worker`. Blob storage is
  a **mounted volume** shared by backend + workers (simplest for a 3-dev on-prem box; MinIO only if
  we ever go multi-node).
- **`ffmpeg` is required** and baked into the backend + ml images: the ingest decode-once step and
  the pyannote/torchcodec path both need the system binary. (faster-whisper bundles PyAV, but the
  diarization/embedding path does not — so ffmpeg must be present.)
- **GPU runtime:** NVIDIA Container Toolkit on the host; **CUDA 12 / cuDNN 9** in the ml image
  (required by faster-whisper's CTranslate2 backend for GPU).
- **Offline gated models (on-prem) — REVISED (2026-07-23, was "bake into the ml image"):** weights
  live in a named **`hf_cache` volume** (`HF_HOME=/hf`) filled once by an explicit warmup one-shot
  (`python -m ml.warmup`, the only container that sees `HF_TOKEN`). `scripts/deploy.sh` runs the
  warmup as a **deploy gate** between `build` and `up`: warm cache → passes offline in ~a minute,
  cold cache → downloads with the token; failure aborts the deploy with the old workers still
  serving. Workers run with `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` and **`ML_DEVICE=cuda`
  pinned** (server overlay `infra/docker-compose.gpu.yml`) so there is **no runtime HuggingFace
  fetch and no silent CPU fallback**. Rationale for the deviation: no +multi-GB image rebuilds on
  the shared box, token never enters image layers, and the gate validates the full CUDA stack
  pre-replacement. One teammate accepts the HF gating conditions once (for `segmentation-3.0` +
  the diarization pipeline). speechbrain ECAPA is ungated, so embeddings need no token.
  Note: the deployed diarization default is `pyannote/speaker-diarization-3.1` (tested by the ML
  implementation; dep pin `pyannote.audio <4`); the community-1 benchmark stays an open ML thread.

## 9. Risks & mitigations (pre-mortem / roast)

### 9.1 "Exact speaker count" is the riskiest requirement
Short classroom utterances (~0.5 s: "yes", "here") produce **unstable ECAPA embeddings** → over/
under-clustering; a ±0.05 threshold shift swings the estimated count. **This is where the grade
risk lives, and it is mostly ML tuning, not architecture.** Mitigations the architecture provides:
the optional **`expected_speakers` hint** (→ exact `n_clusters`), averaging embeddings per speaker,
a **min-turns/min-duration** gate before minting a new speaker, and threshold tuning on a labeled
hour. **Be honest with graders: exact-N is best-effort (the stretch tier).**

### 9.2 Stitching needs a global barrier
Speaker IDs cannot be finalized until every chunk is mapped (clustering needs all embeddings). This
is inherent, and fine — embeddings are tiny. The FE shows a `stitching` stage so it's visible.

### 9.3 Chunk boundaries split turns/words
A 5 s **overlap** preserves cross-seam context; the reduce step **dedupes** the doubled overlap
region and merges a turn's two partial embeddings.

### 9.4 Short utterances → weak embeddings (see 9.1)
Min-turn-duration policy; low-confidence turns get lumped or left unassigned rather than spawning
phantom speakers.

### 9.5 pyannote gating × 3 devs + CI + on-prem
Embeddings use ungated ECAPA; diarization weights are cached offline in the `hf_cache` volume via
the warmup gate (see §8); the one-time token setup is documented. Nobody is blocked on a gating
form mid-sprint.

### 9.6 200 MB mp3 decode + ffmpeg dependency
**Decode once** to 16 kHz mono WAV at ingest; keep mp3 only for playback; ffmpeg baked into images.

### 9.7 Job reliability
Retries + idempotent upserts + Postgres-as-truth mean a worker crash or a single bad chunk never
corrupts a recording or wedges the pipeline.

### 9.8 GPU bottleneck / single point
Pool sized to GPUs; realistic throughput expectations set (§4.4); multi-GPU unlocks real parallelism.

### 9.9 Barrier race & CUDA-fork
Atomic decrement (§7.3) and `SimpleWorker` / solo pool (§7.2) — both are classic footguns, both
pre-empted.

### 9.10 Timeline volume
A 2-hour lecture is thousands of segments — fine as JSON; downsample **for the player only** if
rendering lags.

### 9.11 The real project risk is the team, not the tech
Three people stalling on each other. Mitigation is baked into the plan: **contracts + a stub ML
worker + fixtures land first**, so FE and BE develop the full flow against fakes before real ML.

## 10. Resolved defaults

Decisions taken here so nobody is blocked; all are cheap to change:

- **Chunk window / overlap:** **45 s / 5 s**, configurable. (Balances diarization context, boundary
  seam count, and progress granularity; the task allows 30–60 s.)
- **Diarization model:** default **`speaker-diarization-community-1`** (better speaker counting);
  `3.1` is the fallback. Friend A benchmarks both.
- **Failure policy:** **v1 hard-fails** a recording if any chunk fails after retries (partial
  timeline is a v2 option).
- **`expected_speakers`:** total distinct speakers **including** the teacher.
- **Teacher = most total speech time.**

## 11. Planned repo layout (next round — not built yet)

```
/
├─ docs/            architecture.md (this file), task.md
├─ contracts/       Pydantic models → JSON Schema → generated TS; fixtures; stub ML worker
├─ backend/         FastAPI app, orchestrator, DB models + Alembic, blob + queue adapters   ← George
├─ ml/              worker entrypoint + pipeline (ASR / diar / embed / stitch)               ← Friend A
├─ frontend/        React (Vite) SPA                                                          ← Friend B
├─ infra/           docker-compose.yml, per-service Dockerfiles (ffmpeg, CUDA), .env.example  ← George
└─ README.md        one-command bring-up + who-owns-what
```

## 12. How to start (once §11 is scaffolded)

- **Friend A (ML):** implement a worker that consumes `transcribe_chunk` and produces the
  [chunk-result shape](#5b-backend--ml-job--result-contract). Develop against the canonical WAV +
  the job contract; you never need to touch the API or the frontend.
- **Friend B (FE):** build the upload → list+status → timeline player against the
  [timeline payload](#5a-frontend--backend-rest--json) and a fixture `timeline.json`. You never wait
  for real ML — the stub worker produces a valid fake timeline.
- **George (BE/infra):** the API, the orchestrator + atomic barrier, Postgres, blob storage, and
  the compose stack — plus the stub worker that unblocks the other two on day one.

The bar for this document: **Friend A and Friend B can each start without asking George a
question.** If a gap makes that impossible, it's a bug in this doc — fix the doc.

## References (primary sources)

Verified during scoping (2026-07):
- **faster-whisper** — API, `word_timestamps`, CUDA 12/cuDNN 9, PyAV: <https://github.com/SYSTRAN/faster-whisper>, PyPI `faster-whisper` 1.2.1.
- **pyannote diarization** (gated; token + conditions; emits labels not embeddings; offline via `HF_HUB_OFFLINE`): <https://huggingface.co/pyannote/speaker-diarization-3.1>, <https://huggingface.co/pyannote/speaker-diarization-community-1>, <https://github.com/pyannote/pyannote-audio>.
- **speechbrain ECAPA** (ungated, 192-dim, offline, GPU): <https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb>.
- **Clustering** (agglomerative, cosine, `n_clusters` vs `distance_threshold`): <https://scikit-learn.org/stable/modules/generated/sklearn.cluster.AgglomerativeClustering.html>.
- **RQ** (v2.10; `SimpleWorker`; job deps): <https://python-rq.org/docs/>. **Celery** chords (alternative): <https://docs.celeryq.dev/en/stable/userguide/canvas.html>.
- **FastAPI/Starlette** — `UploadFile` streaming + `FileResponse` HTTP Range: <https://fastapi.tiangolo.com/tutorial/request-files/>, Starlette `responses.py`.
- **Rejected/alternatives** — WhisperX (whole-file in memory): <https://github.com/m-bain/whisperx>; NeMo Sortformer (streaming diarization): <https://github.com/NVIDIA/NeMo>.
