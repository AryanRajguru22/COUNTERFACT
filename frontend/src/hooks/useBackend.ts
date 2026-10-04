import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { Incident, MetricSeries, SystemModel } from "../types";

export interface BackendState {
  /** null until the first answer. */
  online: boolean | null;
  llmMode: string | null;
  /** Fixture problems the backend reports through /health (503), if any. */
  healthError: string | null;
  incidents: Incident[];
  recheck: () => void;
}

const HEALTH_MS = 8000;

/** Backend reachability, the LLM mode it runs in, and the incident catalogue. */
export function useBackend(): BackendState {
  const [online, setOnline] = useState<boolean | null>(null);
  const [llmMode, setLlmMode] = useState<string | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const check = async () => {
      try {
        const health = await api.health();
        if (cancelled) return;
        setOnline(true);
        setLlmMode(health.llm_mode);
        setHealthError(null);
        const list = await api.listIncidents();
        // keep the same array when nothing changed, so the 8 s health poll does not re-render the app
        if (!cancelled) setIncidents((prev) => (JSON.stringify(prev) === JSON.stringify(list) ? prev : list));
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiError && error.status === 503) {
          setOnline(true); // reachable, but its fixtures are broken
          setHealthError(error.detail);
        } else {
          setOnline(false);
        }
      }
      timer = setTimeout(check, HEALTH_MS);
    };
    void check();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [tick]);

  const recheck = useCallback(() => setTick((n) => n + 1), []);
  return { online, llmMode, healthError, incidents, recheck };
}

export interface IncidentData {
  model: SystemModel | null;
  metrics: MetricSeries[];
  error: string | null;
}

const cache = new Map<string, IncidentData>();

/** SLO/system model and observed telemetry for an incident. Cached per incident for the page's lifetime. */
export function useIncidentData(incidentId: string | null): IncidentData {
  const [data, setData] = useState<IncidentData>({ model: null, metrics: [], error: null });

  useEffect(() => {
    if (!incidentId) {
      setData({ model: null, metrics: [], error: null });
      return;
    }
    const cached = cache.get(incidentId);
    if (cached) {
      setData(cached);
      return;
    }
    let cancelled = false;
    Promise.all([api.systemModel(incidentId), api.metrics(incidentId)])
      .then(([model, metrics]) => {
        const next = { model, metrics, error: null };
        cache.set(incidentId, next);
        if (!cancelled) setData(next);
      })
      .catch((error: Error) => {
        if (!cancelled) setData({ model: null, metrics: [], error: error.message });
      });
    return () => {
      cancelled = true;
    };
  }, [incidentId]);

  return data;
}
