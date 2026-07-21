# frontend — Friend B's home

`public/index.html` is a throwaway placeholder that proves the nginx `/api`
wiring. Replace this directory with the React SPA (Vite as a *build tool* is
fine — the deployed artifact is a static build served by nginx; there is no
dev-server in the deployed topology and no CORS anywhere).

Day-one materials:

- **Types:** `contracts/generated/contracts.ts` — generated from the backend's
  Pydantic models; never edit by hand.
- **Fixtures:** `contracts/fixtures/timeline.json`, `recordings_list.json` —
  schema-valid payloads to build against before the stack is up.
- **API:** 5 endpoints under `/api` (same origin), see `docs/architecture.md`
  §5A. Poll `GET /api/recordings/{id}` every 2–3 s until status is terminal.
- **Rendering rules:** gaps between segments = silence (paint gray);
  `role == "teacher"` = red; each `student_N` gets a distinct dimmed color —
  the palette is yours, the stable ids are the backend's.
- **Audio:** `GET /api/recordings/{id}/audio` supports HTTP Range — a plain
  `<audio>` element seeks correctly.

When the SPA lands: add a node build stage to `infra/dockerfiles/frontend.Dockerfile`
and COPY the build output into `/usr/share/nginx/html`.
