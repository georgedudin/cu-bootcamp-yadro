# YADRO — local lecture ASR + speaker diarization

On-prem service that transcribes lecture audio chunk-by-chunk (faster-whisper)
and keeps every speaker's ID stable across the whole recording. Full design:
[`docs/architecture.md`](docs/architecture.md) · graded brief: [`docs/task.md`](docs/task.md).

**Status:** deployed to the bootcamp box with auto-deploy from `main`. Backend,
orchestration and frontend are real end-to-end; the ML pipeline is a CPU stub
until the real one lands. The box URL is pinned in the team chat — the repo is
public, so no IPs/ports here.

## Golden rules

1. **Never commit to `main` directly.** Branch → PR → CI green → merge.
2. **Merging to `main` redeploys the shared box within ~2 min.** Merge means
   "ship it" — if you're not ready to see it live, don't merge.
3. CI gates every PR: pytest · contracts drift · frontend build. Red = fix first.
4. **Tests must be deterministic** — no random/uuid/time-seeded data, ever.
5. Broke prod? `git revert` the commit on `main` and push — the pipeline
   redeploys the previous state. Never hotfix on the server.
6. Wire types change only in `contracts/src/contracts/` + `make contracts`
   in the same PR — never edit generated files by hand.

## Your lane

| Area | Owner | Start here |
|------|-------|-----------|
| ML pipeline | **Friend A** | [`ml/README.md`](ml/README.md) — implement 2 pure functions, flip 1 import |
| Frontend | **Friend B** | [`frontend/README.md`](frontend/README.md) — working SPA, rework at will |
| Backend / infra / merges | George | `backend/`, `core/`, ml glue + worker, `infra/`, CI |

What's left (as of 2026-07-22):

- **Friend A:** real `transcribe_chunk` + `stitch` (faster-whisper + pyannote +
  ECAPA + clustering), then the GPU bits — grep `FRIEND A` in `infra/`.
- **Friend B:** rework the SPA however you like; the 5 endpoints and rendering
  rules in `frontend/README.md` are the only fixed parts.
- Cross-cutting: nothing — contracts are locked, the whole loop runs with the stub.

## Run it locally

```bash
make up      # full stack in docker: UI http://localhost:8080, API :8000
make down    # stop (V=1 also wipes DB/blob volumes)
make test    # python unit tests (contracts, core, backend, ml)
```

Requires Docker; nothing else. Upload an mp3 in the UI and watch it walk
`uploaded → queued → processing n/m → stitching → done`, then click the row
for the timeline + transcript.

Frontend dev loop (hot reload):

```bash
make up                                    # API on :8000
cd frontend && npm install && npm run dev  # Vite proxies /api -> :8000
```

Need a test file?
`ffmpeg -f lavfi -i "sine=frequency=440:duration=100" -q:a 9 lecture.mp3`

macOS note: `make test` keeps the venv in `~/.venvs/cu-bootcamp-yadro`, not
`./.venv` — iCloud + uv mark in-repo venv files hidden and Python 3.13 then
silently skips `.pth` files.

## Ship & check prod

1. Merge the PR → watch the **Actions** tab: `test` then `deploy` (~1–2 min).
2. Open the box UI (URL in team chat); `/api/health` must answer `ok`.
3. Smoke it: upload an mp3 → status walks to `done` → timeline renders.
4. DB/blob volumes persist across deploys; Alembic migrations run at backend
   startup. Host ports live in the server's `infra/.env` (six teams share the
   box — don't squat defaults). Deploy secrets live only in GitHub Actions.

Manual/emergency deploy: SSH in, `cd ~/cu-bootcamp-yadro && git pull && bash
scripts/deploy.sh`.

## Contracts workflow (the one shared seam)

Pydantic models in `contracts/src/contracts/` are the single source of truth.

```bash
make contracts        # regenerate schema/ + generated/contracts.ts
make contracts-check  # CI gate: artifacts must match the models (git diff)
```

Generated artifacts are **committed** (Friend B never needs Python). Changed a
model? Regenerate and commit in the same PR, or CI goes red.

## GPU (Friend A's lane, but everyone should know)

**The code stays 1080-friendly: `ASR_COMPUTE_TYPE=int8` is the default.**
Pascal (CC 6.1) can't run float16 — CTranslate2 needs CC ≥ 7.0
([quantization docs](https://opennmt.net/CTranslate2/quantization.html)). The
bootcamp box (RTX A4000, shared by 6 teams) may opt into float16 via
`infra/.env` — never in code defaults. Full checklist: `ml/README.md` + grep
`FRIEND A` in `infra/`.

Dev machines are Macs — images are always built on the deploy server (arm64
images won't run there); the CPU stub keeps the local loop fully functional.

## Repo map

```
contracts/  wire types (Pydantic -> JSON Schema -> TS) + fixtures — the locked seams
core/       shared DB layer: models, session, atomic barrier, Alembic
backend/    FastAPI: 5 endpoints, ffmpeg decode-once ingest, RQ enqueue
ml/         worker (RQ SimpleWorker) + DB glue + pipeline/ (Friend A) — ml/README.md
frontend/   React+Vite SPA (Friend B) — frontend/README.md
infra/      docker-compose, Dockerfiles, nginx, .env.example
docs/       architecture.md (the design contract) · task.md (graded brief)
```
