"""Evidence gathering. Owner: Vinayak.

FOUNDATION STUB: a hard-coded evidence catalogue for INC-2041. The real engine
derives these from events.json and metrics.json; the signature is frozen.
"""

from __future__ import annotations

from contracts.models import Evidence, Hypothesis

_CATALOGUE: dict[str, list[Evidence]] = {
    "INC-2041": [
        Evidence(id="EV-01", kind="trace", weight=0.9, source_event_ids=["E-005"],
                 description="Pool-acquire wait accounts for >90% of checkout request time from 14:31 to 14:52.",
                 stance={"H1": "supports", "H3": "refutes", "H4": "refutes"}),
        Evidence(id="EV-02", kind="metric", weight=0.9, source_event_ids=["E-001", "E-004"],
                 description="Active pool connections pinned at 10/10 from 14:30.",
                 stance={"H1": "supports"}),
        Evidence(id="EV-03", kind="config_diff", weight=0.8, source_event_ids=["E-001"],
                 description="CHG-881 reduced db.pool.max from 50 to 10 at 14:05.",
                 stance={"H1": "supports"}),
        Evidence(id="EV-04", kind="metric", weight=0.8, source_event_ids=["E-004", "E-005", "E-009", "E-010"],
                 description="Error onset (14:31) follows the batch start (14:30); recovery follows the batch end.",
                 stance={"H1": "supports"}),
        Evidence(id="EV-05", kind="deploy_record", weight=0.9, source_event_ids=["E-008"],
                 description="Rollback to v2.4.0 at 14:40 did not change the error rate.",
                 stance={"H2": "refutes"}),
        Evidence(id="EV-06", kind="metric", weight=0.7, source_event_ids=["E-002"],
                 description="v2.4.0 and v2.4.1 pods show the same error rate.",
                 stance={"H2": "refutes"}),
        Evidence(id="EV-07", kind="trace", weight=0.9, source_event_ids=["E-003"],
                 description="Gateway-call spans are normal (p99 ~320 ms); failing requests never reach the gateway call.",
                 stance={"H3": "refutes"}),
        Evidence(id="EV-08", kind="external", weight=0.6, source_event_ids=["E-003"],
                 description="The gateway notice is EU-only, but errors are global.",
                 stance={"H3": "refutes"}),
        Evidence(id="EV-09", kind="metric", weight=0.85, source_event_ids=[],
                 description="DB CPU ~30% and server-side connections 18 of 200: the client is starved, not the server.",
                 stance={"H4": "refutes", "H1": "supports"}),
        Evidence(id="EV-10", kind="deploy_record", weight=0.3, source_event_ids=["E-002"],
                 description="v2.4.1 was deployed 11 minutes before error onset.",
                 stance={"H2": "supports"}),
        Evidence(id="EV-11", kind="external", weight=0.3, source_event_ids=["E-003"],
                 description="The gateway provider posted a latency notice at 14:28.",
                 stance={"H3": "supports"}),
        Evidence(id="EV-12", kind="log", weight=0.3, source_event_ids=["E-006"],
                 description="Error logs show database-related timeouts.",
                 stance={"H4": "supports", "H1": "supports"}),
    ],
}


def gather_evidence(incident_id: str, hypothesis: Hypothesis) -> list[Evidence]:
    return [e for e in _CATALOGUE.get(incident_id, []) if hypothesis.id in e.stance]
