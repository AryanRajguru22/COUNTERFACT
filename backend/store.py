"""In-memory investigation store. Owner: Rohit. No database by design."""

from __future__ import annotations

import threading

from contracts.models import Investigation


class InvestigationStore:
    def __init__(self) -> None:
        self._items: dict[str, Investigation] = {}
        self._lock = threading.Lock()

    def get(self, investigation_id: str) -> Investigation | None:
        with self._lock:
            return self._items.get(investigation_id)

    def put(self, investigation: Investigation) -> None:
        # Store a snapshot so readers never see an object the orchestrator is still mutating.
        snapshot = investigation.model_copy(deep=True)
        with self._lock:
            self._items[snapshot.id] = snapshot


store = InvestigationStore()
