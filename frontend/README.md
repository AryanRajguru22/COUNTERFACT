# frontend/ (owner: Aryan)

Vite + React + TypeScript + Tailwind 3. The UI is the Stitch project "COUNTERFACT: Forensic Incident Lab" (the *Visual Forensic Motion Workspace* screen, in the project's cyan design system), rebuilt as typed components over the API contract.

```bash
npm install
npm run dev          # http://localhost:5173, /api proxied to 127.0.0.1:8000
npm run typecheck
npm test             # vitest: pure derivations, formatters, report builder
npm run build
```

For a build served from a different origin than the backend, set `VITE_API_BASE_URL` (default `/api`) at build time; see the Deployment section of the root README.

Start the backend from the repository root first: `python -m uvicorn backend.main:app --port 8000`.

## Layout

| Path | What |
| --- | --- |
| `src/types.ts` | Hand mirror of `contracts/models.py`. Update it whenever the contract changes. |
| `src/api.ts` | Typed client. `ApiError.status === 0` means the backend is unreachable. |
| `src/hooks/` | `useInvestigation` (1 s polling, skips unchanged snapshots), `useBackend` (health, incidents, SLO and telemetry), browser helpers (hash route, reduced motion). |
| `src/lib/derive.ts` | Pure derivations: pipeline state, breach window, event classes, outcomes. Unit-tested. |
| `src/components/` | Shell (header, sidebar, stage ribbon), agent drawer, shader background, charts (`ErrorChart`, `TimelineStrip`). |
| `src/views/` | One file per screen: Start, Overview, Timeline, Hypotheses, Evidence, Root Cause, Lab, Gate, Verification. |

## Behaviour worth knowing

- The URL hash is the route (`#/<investigation id>/<view>`), so a refresh keeps the run and the screen. A run the backend no longer knows about (it keeps runs in memory) returns to the start screen with a notice.
- **Follow live** moves to the view that shows the agent's current stage. Clicking any view takes control; the ribbon button resumes following.
- The Lab combines interventions (tick boxes) through `POST /api/simulate` and replays history with a scrubbable playhead.
- The Gate approves or rejects any ranked row. A rejection needs a note (validated client-side, and the server's 409/422/400 `detail` is shown inline). After a failed verification or a rejection the ranking shrinks and the attempt count shows.
- Motion respects `prefers-reduced-motion`; the WebGL background pauses when the tab is hidden and only fades in after its first rendered frame.
- Exports are client-side: timeline, evidence and comparison CSVs, and a Markdown incident report built from the investigation.
- Read-only endpoints used for charts: `GET /api/incidents/{id}/system-model` (SLO) and `GET /api/incidents/{id}/metrics` (observed telemetry).

Only Aryan runs `npm install <package>`.
