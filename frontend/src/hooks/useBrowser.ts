import { useCallback, useEffect, useState } from "react";
import { isViewId, type ViewId } from "../lib/derive";

/** True when the user asked the OS for reduced motion. Components skip decorative animation then. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!query) return;
    const onChange = () => setReduced(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

export interface Route {
  investigationId: string | null;
  view: ViewId;
}

/** `#/<investigation id>/<view>`: a refresh or a shared link lands on the same run and screen. */
function parseHash(hash: string): Route {
  const [, id, view] = hash.replace(/^#/, "").split("/");
  return { investigationId: id || null, view: view && isViewId(view) ? view : "overview" };
}

export function useHashRoute(): [Route, (next: Partial<Route>) => void] {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));

  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const navigate = useCallback((next: Partial<Route>) => {
    setRoute((current) => {
      const merged = { ...current, ...next };
      const hash = merged.investigationId ? `#/${merged.investigationId}/${merged.view}` : "#/";
      if (window.location.hash !== hash) window.history.replaceState(null, "", hash);
      return merged;
    });
  }, []);

  return [route, navigate];
}

/** A localStorage-backed string. Storage can throw (private windows), so every access is guarded. */
export function useStoredString(key: string, fallback: string): [string, (value: string) => void] {
  const [value, setValue] = useState(() => {
    try {
      return window.localStorage.getItem(key) ?? fallback;
    } catch {
      return fallback;
    }
  });
  const set = useCallback(
    (next: string) => {
      setValue(next);
      try {
        window.localStorage.setItem(key, next);
      } catch {
        // storage unavailable: keep the in-memory value
      }
    },
    [key],
  );
  return [value, set];
}
