# Demo script (owner: Aryan)

Central line: **"COUNTERFACT doesn't stop at explaining why the incident happened. It tests what would have prevented it."**

The happy path takes 1 to 2 minutes. Everything runs in Replay mode: no network, no API key. The replan beat at the end is optional (about 30 s extra).

## Before you go on stage

1. Backend: `python -m uvicorn backend.main:app --port 8000` (repository root). Frontend: `npm run dev` in `frontend/`, then open http://localhost:5173.
2. Check `http://127.0.0.1:8000/api/health` returns `{"ok": true, "llm_mode": "replay"}`.
3. Leave the mode on **Replay**. Use a full-size desktop window.
4. Pacing: the agent takes about 27 s to reach the approval gate, and about 4 s from approval to *Resolved*. The UI follows the agent on its own (**Following live**), so talk through steps 2 to 6 while it moves.
5. Run state lives in backend memory. If you restart the backend, start a new run.

## Happy path

**1. Start with INC-2041**
- ACTION: On the start screen, select INC-2041 with **Replay** on, then press **Investigate**.
- SAY: "Checkout payments are failing. Five-xx rate went over the 5% SLO. COUNTERFACT investigates it, and nothing it does touches real infrastructure."
- IMPORTANT: Sev1, `payment-svc`, replay mode.
- AVOID: Switching to **Live**; it falls back to the same recordings.

**2. What failed (Overview)**
- ACTION: Stay on Overview as it appears.
- SAY: "Here's what failed: errors peaked near 38% and the SLO was breached for 22 minutes."
- IMPORTANT: Peak 38.0% and a 22-minute breach (14:32 to 14:54 UTC).
- AVOID: Clicking around while the agent is still working.

**3. Timeline**
- ACTION: Let the view follow to **Timeline**, or click it.
- SAY: "The agent rebuilt the timeline. Three events changed system state: CHG-881 cut the pool from 50 to 10, then the settlement batch job started, then ended."
- IMPORTANT: The highlighted state-changing events E-001, E-004 and E-009.

**4. Competing hypotheses**
- ACTION: **Hypotheses**.
- SAY: "Four competing explanations. Three are rejected: code regression in v2.4.1, gateway degradation and database overload."
- IMPORTANT: H1 confirmed at 95%, H2 to H4 rejected at 9% to 12%.

**5. Evidence**
- ACTION: **Evidence**; scroll once.
- SAY: "Every verdict is backed by evidence the agent gathered, 17 items in all."
- IMPORTANT: The 17 evidence items. Click one only if asked.

**6. Root cause**
- ACTION: **Root Cause**.
- SAY: "Root cause: connection-pool exhaustion. CHG-881 cut the pool from 50 to 10 at 14:05, then the settlement batch took 8 connections at 14:30, so checkouts queued, timed out and retried."
- IMPORTANT: The causal chain starts at E-001 (CHG-881); the statement is supported by 9 evidence items and none against it.

**7. Open the Counterfactual Lab**
- ACTION: **Counterfactual Lab**.
- SAY: "Now the real question: what would have prevented it? These are the interventions, each simulated against the same incident."
- IMPORTANT: Five candidates; "3 of 5 candidate fixes would have prevented the 22-minute outage."
- AVOID: Reading the legend aloud. The dashed grey line is observed telemetry; the red line is the simulated baseline.

**8. I5 = NO EFFECT**
- ACTION: Click the **I5: Roll back v2.4.1** card.
- SAY: "The obvious first response, rolling back the latest deploy, changes nothing. The simulation reproduces the outage exactly."
- IMPORTANT: **NO EFFECT**, peak 38.7%, 22 min, the same as the baseline.

**9. The simulated alternatives**
- ACTION: Click **I1**, then optionally **I2** and **I4**. Press **Replay history** once.
- SAY: "Reverting the pool size, moving the batch job off-peak and a capacity guardrail all stay under the SLO for the whole window. Retry budget (I3) only trims it: 20 minutes still breach."
- IMPORTANT: I1, I2, I4 show 0 breach minutes. I3 shows a peak of 18.9% and 20 min.
- AVOID: Ticking combination boxes. They work, but they are not part of the story.

**10. Why I1 is ranked first**
- ACTION: Press **Review recommended intervention (I1)**.
- SAY: "Three fixes prevent the whole outage. I1 ranks first because it's the cheapest and lowest risk: 15 minutes of effort."
- IMPORTANT: Score 21.88 for I1, against 21.75 for I2 and 20 for I4. The score is breach minutes avoided, minus a risk penalty, minus 0.5 per effort hour.

**11. Approve I1**
- ACTION: At the Gate, leave the approver as is, then press **Approve & execute verification**.
- SAY: "A human signs off. The change is applied to the simulated environment only."
- IMPORTANT: "Will apply (simulated environment only): `set_param pool_size = 50`."

**12 and 13. Execute and verify**
- ACTION: Wait about 4 s; the view moves to **Execution & Verification** by itself.
- SAY: "It executes, then verifies: it replays the incident on the changed system, then again with 20% more demand."
- IMPORTANT: **VERIFIED - PASSED**. All three checks pass: breach minutes 0, peak error rate 0, and 0 breach minutes at +20% demand.

**End here:** the investigation is *Resolved*. If you are not doing the replan beat, stop on this screen.

## Optional replan beat (I3 fails, the agent replans)

Use this on a fresh run, before approving I1. It adds about 30 s.

**R1. Pick the weak fix**
- ACTION: At the Gate, click the **I3: Retry budget with jitter** row, then press **Approve & execute verification**.
- SAY: "Let's say the operator picks the retry budget instead. The gate warns that it's not the recommendation."
- IMPORTANT: The amber notice: "I3 is not the recommendation".

**R2. Verification fails and the agent replans**
- ACTION: Wait a few seconds; the page returns to the Gate.
- SAY: "Verification fails, so the agent doesn't stop. It drops I3, re-simulates the rest and re-ranks."
- IMPORTANT: The banner "Attempt 1 of 3: I3 failed verification" with its failing checks (breach minutes 20, peak 0.189, 27 breach minutes at +20% demand), and "4 options remain".

**R3. Approve I1 after the replan**
- ACTION: I1 is back as the top-ranked recommendation. Press **Approve & execute verification**.
- SAY: "I1 is recommended again and this time it holds."
- IMPORTANT: Final state **Resolved**, verified, "Resolved after 2 approval attempts".

## Things not to do

- Do not press **Reject** on stage unless you have a note ready: a rejection needs one, and it triggers a replan too. Two rejections in a row can end the run in *failed* (the cap is 3 approval attempts).
- Do not refresh mid-run after restarting the backend; the run is gone and you are sent back to the start screen.
- Do not claim the simulation was calibrated to the minute: its ramp is steadier than the observed telemetry (the grey dashed line), though the window and the peak match.

## Click path in the built UI (reference)

1. Start screen: pick INC-2041, leave **Replay**, press **Investigate**. The UI follows the agent through Timeline, Hypotheses, Evidence, Root Cause and the Lab on its own; click any stage to take over, and press **Follow live** to catch up.
2. Lab: select I5 to see the rollback change nothing, tick I1 and I3 to simulate the combination, and press **Replay history** to watch the playhead cross the breach.
3. Gate: **Approve** the recommendation to reach *Resolved*, or pick the I3 row and approve it to see verification fail and the ranking shrink (the replan path). **Reject** needs a note.
4. Verification: checks, stress test, applied changes, and **Download report**.
