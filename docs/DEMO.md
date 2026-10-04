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
