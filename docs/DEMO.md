# Demo script (owner: Aryan)

Only this path has to work on stage. The rest can be cut.

1. Open INC-2041 "Checkout payments failing" and press **Investigate**.
2. The timeline renders, and the state-changing events (CHG-881, batch start and end) are highlighted.
3. Four hypotheses appear, and H2, H3 and H4 are visibly rejected with their refuting evidence.
4. The root cause (H1, pool exhaustion) appears with its causal chain.
5. In the Counterfactual Lab, the baseline curve is shown against each intervention. The ranked table shows that the rollback (I5) does nothing.
6. The system makes a recommendation, and the operator presses **Approve**.
7. The fix is executed and verified with a stress test, and the result shows PASSED.

The agent reasoning panel runs alongside the whole flow.

The first stretch goal is replanning. The operator approves I3, verification fails, and the system re-ranks.

## Click path in the built UI

1. Start screen: pick INC-2041, leave **Replay**, press **Investigate**. The UI follows the agent through Timeline, Hypotheses, Evidence, Root Cause and the Lab on its own; click any stage to take over, and press **Follow live** to catch up.
2. Lab: select I5 to see the rollback change nothing, tick I1 and I3 to simulate the combination, and press **Replay history** to watch the playhead cross the breach.
3. Gate: **Approve** the recommendation to reach *Resolved*, or pick the I3 row and approve it to see verification fail and the ranking shrink (the replan path). **Reject** needs a note.
4. Verification: checks, stress test, applied changes, and **Download report**.

