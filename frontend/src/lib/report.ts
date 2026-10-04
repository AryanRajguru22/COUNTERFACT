import { baselineOf, describeAction, interventionTitle } from "./derive";
import { clock, minuteLabel, pct, pctWhole } from "./format";
import type { Investigation } from "../types";

/** A plain-Markdown incident report built only from what the investigation actually produced. */
export function buildReport(inv: Investigation): string {
  const lines: string[] = [];
  const baseline = baselineOf(inv.simulations);
  const rc = inv.root_cause;
  lines.push(`# ${inv.incident.id}: ${inv.incident.title}`, "");
  lines.push(`- Service: ${inv.incident.service}`, `- Severity: ${inv.incident.severity}`, `- Detected: ${clock(inv.incident.detected_at)} UTC`);
  lines.push(`- Investigation: ${inv.id} (${inv.mode} mode, stage: ${inv.stage})`, "", inv.incident.summary, "");

  if (rc) {
    const h = inv.hypotheses.find((x) => x.id === rc.hypothesis_id);
    lines.push(`## Root cause (${pctWhole(rc.confidence)} confidence)`, "", `**${h?.title ?? rc.hypothesis_id}**`, "", rc.statement, "", "### Causal chain", "");
    rc.causal_chain.forEach((link, i) => {
      const event = inv.timeline.find((e) => e.id === link.event_id);
      const at = event ? ` (${minuteLabel(inv.incident.window.start, event.t)} UTC)` : "";
      lines.push(`${i + 1}. **${link.event_id}**${at}: ${link.effect}`);
    });
    if (rc.contributing_factors.length) {
      lines.push("", "### Contributing factors", "", ...rc.contributing_factors.map((f) => `- ${f}`));
    }
    lines.push("");
  }

  const rejected = inv.hypotheses.filter((h) => h.status === "rejected");
  if (rejected.length) {
    lines.push("## Hypotheses ruled out", "", ...rejected.map((h) => `- **${h.id} ${h.title}** (${pctWhole(h.confidence)}): ${h.rejection_reason ?? "rejected"}`), "");
  }

  if (inv.ranking.length || baseline) {
    lines.push("## Counterfactual results", "");
    if (baseline) lines.push(`Baseline: peak ${pct(baseline.peak_error_rate)}, ${baseline.breach_minutes} breach minutes.`, "");
    for (const r of inv.ranking) {
      lines.push(`${r.rank}. **${r.intervention_id} ${interventionTitle(inv, r.intervention_id)}**: ${r.prevented ? "prevents the breach" : "does not prevent the breach"}, avoids ${r.breach_minutes_avoided} breach minutes (score ${r.score}).`);
    }
    lines.push("");
  }

  if (inv.approval) {
    lines.push("## Decision", "", `${inv.approval.approver} ${inv.approval.decision} **${inv.approval.intervention_id}**${inv.approval.at ? ` at ${inv.approval.at}` : ""}${inv.approval.note ? `: ${inv.approval.note}` : "."}`, "");
  }
  if (inv.execution) {
    lines.push("## Execution (simulated environment only)", "", ...inv.execution.applied_changes.map((c) => `- ${describeAction(c)}`), `- Status: ${inv.execution.status}`, "");
  }
  if (inv.verification) {
    lines.push(`## Verification: ${inv.verification.passed ? "PASSED" : "FAILED"}`, "");
    for (const c of inv.verification.checks) lines.push(`- ${c.passed ? "PASS" : "FAIL"} ${c.name}: expected ${c.expected}, observed ${c.observed}`);
    lines.push(`- ${inv.verification.stress_test_passed ? "PASS" : "FAIL"} stress test`, "");
  }
  return lines.join("\n");
}
