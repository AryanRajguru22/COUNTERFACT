// Small, pure formatters. All clock times are UTC, because the contract's timestamps are UTC.

const pad = (n: number) => String(n).padStart(2, "0");

/** "14:05" for an ISO timestamp. Empty string for anything unparseable. */
export function clock(iso: string): string {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "";
  const d = new Date(ms);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

/** "14:05:12" for an ISO timestamp. */
export function clockSeconds(iso: string): string {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "";
  const d = new Date(ms);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

/** Wall-clock label for minute index `t` of a window that starts at `windowStart`. */
export function minuteLabel(windowStart: string, t: number): string {
  const base = Date.parse(windowStart);
  if (Number.isNaN(base)) return `t+${t}`;
  return clock(new Date(base + t * 60_000).toISOString());
}

/** Error-rate ratio as a percentage: 0.382 -> "38.2%". Small values keep a second decimal: 0.0098 -> "0.98%". */
export function pct(ratio: number, digits?: number): string {
  const value = ratio * 100;
  const d = digits ?? (Math.abs(value) < 10 ? 2 : 1);
  return `${value.toFixed(d)}%`;
}

/** A 0..1 score as a whole-number percentage: 0.954 -> "95%". */
export function pctWhole(ratio: number): string {
  return `${Math.round(ratio * 100)}%`;
}

export function minutes(n: number): string {
  return `${n} min`;
}

/** 0.25 -> "15 min", 4 -> "4 h", 0.5 -> "30 min". */
export function effort(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)} min`;
  return Number.isInteger(hours) ? `${hours} h` : `${hours.toFixed(1)} h`;
}

export function compactNumber(n: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(Math.round(n));
}

/** "payment_svc.pool_size" style keys -> readable words. */
export function humanize(key: string): string {
  return key.replace(/[_.]+/g, " ").replace(/\s+/g, " ").trim();
}

export function titleCase(text: string): string {
  return text.replace(/\b\w/g, (c) => c.toUpperCase());
}
