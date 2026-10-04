import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { isTerminal } from "../lib/derive";
import type { Investigation } from "../types";

const POLL_MS = 1000;
const OFFLINE_RETRY_MS = 2000;

export interface InvestigationState {
  investigation: Investigation | null;
  /** True while the first fetch for this id is in flight. */
  loading: boolean;
  /** The id does not exist on the backend (typically it restarted: the store is in memory). */
  gone: boolean;
  /** The backend could not be reached on the last poll. The last good snapshot stays on screen. */
  offline: boolean;
  /** Replace the snapshot with a fresher one (the approval response) and resume polling. */
  accept: (next: Investigation) => void;
  /** Resume polling after a state change that moves a terminal run on (not needed for approvals). */
  poke: () => void;
}

/**
 * Polls GET /api/investigations/{id} every second until the run is resolved or failed.
 * The snapshot is replaced only when its content changed, so memoised views and chart animations stay still
 * between real updates.
 */
export function useInvestigation(id: string | null): InvestigationState {
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [loading, setLoading] = useState(false);
  const [gone, setGone] = useState(false);
  const [offline, setOffline] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const lastJson = useRef("");

  const store = useCallback((next: Investigation) => {
    const json = JSON.stringify(next);
    if (json === lastJson.current) return;
    lastJson.current = json;
    setInvestigation(next);
  }, []);

  useEffect(() => {
    lastJson.current = "";
    setInvestigation(null);
    setGone(false);
    setOffline(false);
    if (!id) {
      setLoading(false);
      return;
    }
    setLoading(true);
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      let delay = POLL_MS;
      try {
        const latest = await api.getInvestigation(id);
        if (cancelled) return;
        setOffline(false);
        setLoading(false);
        store(latest);
        if (isTerminal(latest.stage)) return; // stop; accept() or poke() restarts
      } catch (error) {
        if (cancelled) return;
        setLoading(false);
        if (error instanceof ApiError && error.status === 404) {
          setGone(true);
          return;
        }
        setOffline(true);
        delay = OFFLINE_RETRY_MS;
      }
      timer = setTimeout(tick, delay);
    };
    void tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [id, epoch, store]);

  const poke = useCallback(() => setEpoch((n) => n + 1), []);
  const accept = useCallback(
    (next: Investigation) => {
      store(next);
      setEpoch((n) => n + 1);
    },
    [store],
  );

  return { investigation, loading, gone, offline, accept, poke };
}
