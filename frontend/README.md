# frontend — Friend B's home

React + Vite + TypeScript + Tailwind SPA. Deployed as a **static build served
by nginx** (which reverse-proxies `/api` to the backend — same origin, no CORS,
no dev-server in the deployed topology). Rework anything you like; the wire
contract below is the only fixed part.

## Dev loop

```bash
make up            # from repo root: full stack in docker (API on :8000)
cd frontend
npm install
npm run dev        # Vite dev server, proxies /api -> localhost:8000
npm run build      # tsc --noEmit + vite build -> dist/  (this is what CI/Docker run)
```

Deployment builds `infra/dockerfiles/frontend.Dockerfile` (node build stage →
nginx). CI runs `npm ci && npm run build` on every PR — a broken build can't
reach `main`.

## The wire contract (fixed)

- **Types:** `contracts/generated/contracts.ts` — generated from the backend's
  Pydantic models; never edit by hand. Imported via the `@contracts` alias
  (`vite.config.ts` + `tsconfig.json`), re-exported in `src/types.ts`.
  Types-only file → always `import type`.
- **Fixtures:** `contracts/fixtures/timeline.json`, `recordings_list.json` —
  schema-valid payloads to build against before the stack is up.
- **API:** 5 endpoints under `/api` (same origin), see `docs/architecture.md`
  §5A. Poll `GET /api/recordings` every 2–3 s until status is terminal.
- **Rendering rules:** gaps between segments = silence (paint gray);
  `role == "teacher"` = red; each `student_N` gets a distinct dimmed color —
  the palette is yours (`src/palette.ts`), the stable ids are the backend's.
- **Audio:** `GET /api/recordings/{id}/audio` supports HTTP Range — a plain
  `<audio>` element seeks correctly.

## File map

```
src/App.tsx                    single page: upload -> list -> timeline panel
src/api.ts                     typed fetch wrappers for the 5 endpoints
src/types.ts                   re-exports from @contracts (single import point)
src/palette.ts                 speaker id -> color (teacher red, students dimmed)
src/hooks/usePoll.ts           chained-setTimeout polling (2.5 s list refresh)
src/components/UploadForm.tsx  mp3 + optional expected_speakers (omitted when blank)
src/components/RecordingsList.tsx  status chips, "3/12" chunk progress, click done row
src/components/TimelinePanel.tsx   audio + track + legend + transcript
src/components/Track.tsx       colored strip, rAF playhead, click-to-seek
src/components/Transcript.tsx  Apple Music-style: current block centered/bright,
                               windowed DOM (~50 nodes for any lecture length),
                               follow/browse modes, click block -> seek
```

Gotcha: never name a source dir `lib/` or `build/` — the **root** `.gitignore`
ignores those names at any depth.
