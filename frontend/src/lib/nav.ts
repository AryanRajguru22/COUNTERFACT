import type { ViewId } from "./derive";

/** What the user has selected, shared across views so a click in one lands on the matching item in another. */
export interface Focus {
  eventId: string | null;
  hypothesisId: string | null;
  evidenceId: string | null;
  /** Interventions plotted in the Counterfactual Lab (one for a single fix, several for a combination). */
  interventionIds: string[];
}

export const EMPTY_FOCUS: Focus = { eventId: null, hypothesisId: null, evidenceId: null, interventionIds: [] };

export interface Nav {
  focus: Focus;
  go: (view: ViewId, focus?: Partial<Focus>) => void;
  setFocus: (focus: Partial<Focus>) => void;
}
