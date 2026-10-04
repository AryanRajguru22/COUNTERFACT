# backend/ (owner: Rohit)

This is the FastAPI app. Run it from the repo root with `uvicorn backend.main:app --reload`.

- `main.py` builds the app, sets CORS for `localhost:5173`, and includes a minimal `.env` loader.
- `routes.py` defines the `/api` endpoints listed in `contracts/CONTRACTS.md`.
- `store.py` is the in-memory investigation store. It holds snapshots only, with no database.

The backend reaches the engines only through `agent/tools.py`.
