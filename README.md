# YADRO — local lecture ASR + speaker diarization

On-prem service that transcribes lecture audio chunk-by-chunk (faster-whisper)
and keeps every speaker's ID stable across the whole recording. Full design:
[`docs/architecture.md`](docs/architecture.md) · graded brief: [`docs/task.md`](docs/task.md).

## Run it

```bash
make up      # builds + starts the whole stack in docker
```

- Frontend (nginx): <http://localhost:8080> — upload an mp3, watch progress
- API direct: <http://localhost:8000/api/health> · docs at `/docs`

`make down` stops it (`make down V=1` also wipes the DB/blob volumes).
Requires Docker; nothing else. The ML worker is currently a **CPU stub** that
produces schema-valid fake transcripts — the whole loop (upload → chunks →
barrier → stitch → timeline) is real.

## Who owns what

| Area | Owner | Where you type |
|------|-------|----------------|
| Backend / orchestration / infra | George | `backend/`, `core/`, `ml/glue.py` + `ml/worker.py`, `infra/` |
| ML pipeline | **Friend A** | `ml/src/ml/pipeline/` — start at [`ml/README.md`](ml/README.md); replace the stub, keep the two pure signatures |
| Frontend | **Friend B** | `frontend/` — see `frontend/README.md`; types in `contracts/generated/contracts.ts` |

The seams (locked in `docs/architecture.md` §5): Friend A's functions are
pure `(job) -> ChunkResult` / `(results, windows, ...) -> StitchResult` and
depend only on `contracts/` — all DB/queue plumbing is George's glue. Friend B
talks to 5 REST endpoints and polls; no CORS, no websockets.

## Contracts workflow

Pydantic models in `contracts/src/contracts/` are the single source of truth.

```bash
make contracts        # regenerate schema/ + generated/contracts.ts
make contracts-check  # CI gate: artifacts must match the models (git diff)
make test             # unit tests (barrier, chunking, stitch identity)
```

Generated artifacts are **committed** so Friend B never needs Python.

## GPU notes

**Requirement: the code stays 1080-friendly.** The baseline GPU target is a
GTX 1080 (Pascal, compute capability 6.1), so `ASR_COMPUTE_TYPE=int8` is the
default everywhere: **float16 will not run on Pascal** (CTranslate2 needs
CC ≥ 7.0; int8 is explicitly supported on 6.1 —
[CTranslate2 quantization docs](https://opennmt.net/CTranslate2/quantization.html)).

The *current* bootcamp box is an RTX A4000 (Ampere, CC 8.6, 16 GB VRAM,
**shared by 6 teams**): float16 works there and may be enabled per-deployment
via `infra/.env` — but int8 stays the default (Pascal-safe, and half the VRAM
on a GPU five other teams are using).

Everything GPU is wired but commented until Friend A's real pipeline lands —
grep `FRIEND A` in `infra/`:

- GPU device reservation + offline HF env: `infra/docker-compose.yml`
- CUDA base image + weight baking: `infra/dockerfiles/ml.Dockerfile`
- pyannote is HF-gated: accept conditions once, bake weights into the image,
  run with `HF_HUB_OFFLINE=1` (no runtime fetches on the box)

Dev machines are Macs — **images are always built on the deploy server**
(arm64 images won't run there; the CI/CD flow below does exactly that). The
stub worker keeps the Mac loop fully functional.

## Deployment & CI/CD

The stack runs on the shared bootcamp server; **every push to `main`
redeploys it** (`.github/workflows/ci.yml`):

```
PR            -> test job  (pytest + contracts drift gate)
push to main  -> test job  -> deploy job: SSH to the server,
                 git reset --hard origin/main, docker compose up -d --build,
                 gate on /api/health, prune dangling images
```

- Secrets (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`) live only in GitHub
  Actions secrets; the deploy key is a dedicated CI keypair, not a personal one.
- Host ports on the shared box are set in the server's `infra/.env`
  (`YADRO_HTTP_PORT`, `YADRO_API_PORT`) — six teams, don't squat defaults.
- **Rollback** = `git revert` the bad commit on `main` and push; the pipeline
  redeploys the previous state. DB volumes persist across deploys; migrations
  run automatically at backend startup.
- Manual/emergency deploy: SSH in, `cd ~/cu-bootcamp-yadro && git pull &&
  bash scripts/deploy.sh`.

## Repo map

```
contracts/  wire types (Pydantic -> JSON Schema -> TS) + fixtures
core/       shared DB layer: models, session, atomic barrier, Alembic
backend/    FastAPI: 5 endpoints, ffmpeg decode-once ingest, RQ enqueue
ml/         worker (RQ SimpleWorker) + DB glue + pipeline/ (Friend A's seam)
frontend/   React + Vite SPA (Friend B) — see frontend/README.md
infra/      docker-compose, Dockerfiles, nginx, .env.example
```

Local venv note (macOS): `make test` keeps the venv in
`~/.venvs/cu-bootcamp-yadro`, not `./.venv` — iCloud-synced folders + uv mark
venv files hidden, and Python 3.13 silently skips hidden `.pth` files.
