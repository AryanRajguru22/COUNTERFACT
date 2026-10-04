# frontend/ (owner: Aryan)

The frontend is built with Vite, React and TypeScript. Run `npm install` and then `npm run dev` to serve it on http://localhost:5173. Requests to `/api` are proxied to `127.0.0.1:8000`.

- `src/types.ts` is a hand mirror of `contracts/models.py`. Update it whenever the contract changes.
- `src/api.ts` is the typed API client.
- `src/App.tsx` is the foundation UI. It has incident select, Investigate, 1-second polling, placeholder sections, and Approve and Reject buttons.

Run `npm run typecheck` before merging to `main`. Only Aryan runs `npm install <package>`.
