import { describe, expect, it } from "vitest";
import {
  breachWindow,
  estimatedFailedRequests,
  eventClass,
  interventionRows,
  niceCeil,
  outcomeOf,
  pipeline,
  simulationFor,
  viewForStage,
} from "./derive";
import { clock, effort, minuteLabel, pct } from "./format";
import { buildReport } from "./report";
import type { Event, Investigation, SimulationResult } from "../types";

const event = (attributes: Event["attributes"], summary = "x"): Event => ({ id: "E-1", ts: "", t: 0, source: "s", kind: "metric", summary, attributes, state_change: null });

const sim = (ids: string[], peak: number, breach: number, prevented: boolean): SimulationResult => ({
  intervention_ids: ids,
  seed: 0,
  series: { error_rate: [], pool_wait_ms: [], inflight: [] },
  peak_error_rate: peak,
  breach_minutes: breach,
  prevented,
});

function investigation(patch: Partial<Investigation> = {}): Investigation {
  return {
    id: "inv-1",
    incident: { id: "INC-1", title: "T", service: "svc", severity: "sev1", started_at: "", detected_at: "2026-09-28T14:32:00Z", resolved_at: null, summary: "S", window: { start: "2026-09-28T14:00:00Z", minutes: 60 } },
    stage: "created",
    mode: "replay",
    timeline: [],
    hypotheses: [],
    evidence: [],
    root_cause: null,
    interventions: [],
    simulations: [],
    ranking: [],
    recommendation: null,
    approval: null,
    execution: null,
    verification: null,
    attempts: 0,
    steps: [],
    error: null,
    ...patch,
  };
}

describe("format", () => {
  it("formats UTC clock times and minute offsets", () => {
    expect(clock("2026-09-28T14:05:00Z")).toBe("14:05");
    expect(minuteLabel("2026-09-28T14:00:00Z", 32)).toBe("14:32");
    expect(minuteLabel("garbage", 3)).toBe("t+3");
  });
  it("formats ratios and effort", () => {
    expect(pct(0.382)).toBe("38.2%");
    expect(pct(0.0098)).toBe("0.98%");
    expect(effort(0.25)).toBe("15 min");
    expect(effort(4)).toBe("4 h");
  });
});

describe("breachWindow", () => {
  it("finds the longest run above the SLO", () => {
    const series = [0, 0, 0.4, 0.4, 0.4, 0, 0.1, 0];
    expect(breachWindow(series, 0.05)).toEqual({ start: 2, end: 5, minutes: 3 });
  });
  it("handles a run that reaches the end and a clean series", () => {
    expect(breachWindow([0, 0.2, 0.2], 0.05)).toEqual({ start: 1, end: 3, minutes: 2 });
    expect(breachWindow([0, 0.01], 0.05)).toBeNull();
  });
});

describe("derivations", () => {
  it("classifies events from the engine's annotations", () => {
    expect(eventClass(event({ causal: true, decoy: false }))).toBe("cause");
    expect(eventClass(event({ causal: false, decoy: true }))).toBe("decoy");
    expect(eventClass(event({ causal: false, decoy: false }, "Recovered"))).toBe("recovery");
    expect(eventClass(event({}, "Alert"))).toBe("symptom");
  });

  it("matches simulations to intervention sets in any order", () => {
    const sims = [sim([], 0.38, 22, false), sim(["I1", "I3"], 0.01, 0, true)];
    expect(simulationFor(sims, ["I3", "I1"])).toBe(sims[1]);
    expect(simulationFor(sims, ["I2"])).toBeUndefined();
  });

  it("scores outcomes against the baseline", () => {
    const base = sim([], 0.38, 22, false);
    expect(outcomeOf(sim(["I1"], 0.01, 0, true), base)).toBe("prevented");
    expect(outcomeOf(sim(["I3"], 0.12, 9, false), base)).toBe("partial");
    expect(outcomeOf(sim(["I5"], 0.38, 22, false), base)).toBe("no_effect");
  });

  it("picks nice axis ceilings and sums failed requests", () => {
    expect(niceCeil(0.382)).toBeCloseTo(0.4);
    expect(niceCeil(0.07)).toBeCloseTo(0.1);
    expect(estimatedFailedRequests([100, 100], [0.5, 0])).toBe(3000);
  });

  it("maps every stage to a view", () => {
    expect(viewForStage("counterfactual")).toBe("lab");
    expect(viewForStage("awaiting_approval")).toBe("gate");
    expect(viewForStage("replanning")).toBe("gate");
    expect(viewForStage("resolved")).toBe("verification");
  });

  it("tracks pipeline progress, including where a failed run stopped", () => {
    const running = pipeline(investigation({ stage: "root_cause" }));
    expect(running.map((s) => s.state)).toEqual(["done", "done", "done", "active", "pending", "pending", "pending"]);
    expect(pipeline(investigation({ stage: "awaiting_approval" }))[5].state).toBe("waiting");
    expect(pipeline(investigation({ stage: "resolved" })).every((s) => s.state === "done")).toBe(true);
    const failed = pipeline(investigation({ stage: "failed", timeline: [event({})] }));
    expect(failed[0].state).toBe("done");
    expect(failed[1].state).toBe("failed");
  });

  it("orders ranked interventions first and joins their simulations", () => {
    const intervention = (id: string) => ({ id, title: id, category: "config" as const, action: { op: "set_param" as const, target: "x", value: 1 }, risk: "low" as const, effort_hours: 1, rationale: "" });
    const inv = investigation({
      interventions: [intervention("I1"), intervention("I2")],
      ranking: [{ intervention_id: "I2", rank: 1, score: 2, prevented: true, breach_minutes_avoided: 5, reasons: [] }],
      simulations: [sim(["I2"], 0.01, 0, true)],
    });
    const rows = interventionRows(inv);
    expect(rows.map((r) => r.intervention.id)).toEqual(["I2", "I1"]);
    expect(rows[0].simulation?.prevented).toBe(true);
    expect(rows[1].ranked).toBeUndefined();
  });
});

describe("report", () => {
  it("builds a report from what the investigation produced and nothing else", () => {
    const text = buildReport(
      investigation({
        stage: "resolved",
        approval: { intervention_id: "I1", decision: "approved", approver: "ana", note: "", at: "2026-10-05T01:00:00+00:00" },
        verification: { intervention_id: "I1", passed: true, stress_test_passed: true, checks: [{ name: "breach minutes", expected: "<= 0", observed: "0", passed: true }] },
      }),
    );
    expect(text).toContain("# INC-1: T");
    expect(text).toContain("ana approved **I1**");
    expect(text).toContain("## Verification: PASSED");
    expect(text).not.toContain("Root cause");
  });
});
