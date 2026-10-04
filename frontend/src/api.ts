// Typed client for the FastAPI backend. Vite proxies /api to http://127.0.0.1:8000.
import type {
  Approval,
  CreateInvestigationResponse,
  HealthResponse,
  Incident,
  Investigation,
  InvestigationMode,
  MetricSeries,
  SimulationResult,
  SystemModel,
} from "./types";

/** Any failed call. `status` is 0 when the backend could not be reached at all. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string, label: string) {
    super(status === 0 ? `Backend unreachable: ${detail}` : `${label}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  get unreachable(): boolean {
    return this.status === 0;
  }
}

/** FastAPI errors are `{"detail": "<message>"}`; its own validation errors are `{"detail": [{"msg": ...}]}`. */
function detailOf(body: string): string | null {
  try {
    const parsed: unknown = JSON.parse(body);
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      const detail = (parsed as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        return detail
          .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
          .join("; ");
      }
    }
  } catch {
    // not JSON: fall through
  }
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method ?? "GET";
  const label = `${method} /api${path}`;
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (cause) {
    throw new ApiError(0, cause instanceof Error ? cause.message : "network error", label);
  }
  if (!response.ok) {
    const body = await response.text();
    const detail = detailOf(body);
    // A 5xx without the backend's JSON body comes from the dev proxy or a gateway: the backend itself is down.
    if (detail === null && response.status >= 500) throw new ApiError(0, `HTTP ${response.status} from the proxy`, label);
    throw new ApiError(response.status, detail ?? (body.trim() || "empty response"), label);
  }
  return response.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<HealthResponse>("/health"),
  listIncidents: () => request<Incident[]>("/incidents"),
  systemModel: (incident_id: string) => request<SystemModel>(`/incidents/${incident_id}/system-model`),
  metrics: (incident_id: string) => request<MetricSeries[]>(`/incidents/${incident_id}/metrics`),
  startInvestigation: (incident_id: string, mode: InvestigationMode = "replay") =>
    post<CreateInvestigationResponse>("/investigations", { incident_id, mode }),
  getInvestigation: (id: string) => request<Investigation>(`/investigations/${id}`),
  submitApproval: (id: string, approval: Approval) => post<Investigation>(`/investigations/${id}/approval`, approval),
  simulate: (incident_id: string, intervention_ids: string[]) =>
    post<SimulationResult>("/simulate", { incident_id, intervention_ids }),
};
