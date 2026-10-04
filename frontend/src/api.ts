// Typed client for the FastAPI backend. Vite proxies /api to http://127.0.0.1:8000.
import type {
  Approval,
  CreateInvestigationResponse,
  HealthResponse,
  Incident,
  Investigation,
  InvestigationMode,
  SimulationResult,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} /api${path} failed: ${response.status} ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<HealthResponse>("/health"),
  listIncidents: () => request<Incident[]>("/incidents"),
  startInvestigation: (incident_id: string, mode: InvestigationMode = "replay") =>
    post<CreateInvestigationResponse>("/investigations", { incident_id, mode }),
  getInvestigation: (id: string) => request<Investigation>(`/investigations/${id}`),
  submitApproval: (id: string, approval: Approval) => post<Investigation>(`/investigations/${id}/approval`, approval),
  simulate: (incident_id: string, intervention_ids: string[]) =>
    post<SimulationResult>("/simulate", { incident_id, intervention_ids }),
};
