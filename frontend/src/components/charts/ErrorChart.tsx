// Error-rate chart used by the overview and the Counterfactual Lab: SVG, measured to its container so text stays crisp.
// Series paths morph (CSS `d` transition, Chromium) when their values change; the first paint reveals left to right.
import { useCallback, useEffect, useId, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type MouseEvent } from "react";
import { niceCeil, type BreachWindow, type EventClass } from "../../lib/derive";
import { minuteLabel, pct } from "../../lib/format";

export interface ChartSeries {
  id: string;
  label: string;
  values: readonly number[];
  color: string;
  dashed?: boolean;
  width?: number;
  area?: boolean;
  opacity?: number;
}

export interface ChartMarker {
  id: string;
  t: number;
  label: string;
  cls: EventClass;
}

interface Props {
  series: readonly ChartSeries[];
  /** Error-rate ceiling drawn as a dashed line; omit (or null) for charts of other quantities. */
  slo?: number | null;
  /** "pct" (default) treats values as ratios; "number" uses `format` for ticks and tooltips. */
  unit?: "pct" | "number";
  format?: (value: number) => string;
  minutes: number;
  windowStart: string;
  breach?: BreachWindow | null;
  markers?: readonly ChartMarker[];
  height?: number;
  yMax?: number;
  /** Minute index of an animated playhead, or null/undefined for none. */
  playhead?: number | null;
  selectedMarker?: string | null;
  onMarkerClick?: (id: string) => void;
  ariaLabel: string;
}

const MARGIN = { top: 34, right: 18, bottom: 26, left: 46 };

export const CLASS_COLOR: Record<EventClass, string> = {
  cause: "#ffb95f",
  symptom: "#ffb4ab",
  decoy: "#869397",
  recovery: "#4edea3",
};

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setWidth(el.clientWidth);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Stagger marker labels onto rows so neighbours do not overprint. */
function markerRows(markers: readonly ChartMarker[], pxPerMinute: number): Map<string, number> {
  const rows = new Map<string, number>();
  const lastEnd: number[] = [-Infinity, -Infinity, -Infinity];
  for (const marker of [...markers].sort((a, b) => a.t - b.t)) {
    const x = marker.t * pxPerMinute;
    const row = lastEnd.findIndex((end) => x >= end + 4);
    const chosen = row === -1 ? 0 : row;
    lastEnd[chosen] = x + marker.id.length * 6.4 + 14;
    rows.set(marker.id, chosen);
  }
  return rows;
}

/** 1, 2, 5 x 10^n at or above `value`. */
function niceNumberCeil(value: number): number {
  if (!(value > 0)) return 1;
  const exponent = Math.floor(Math.log10(value));
  const fraction = value / 10 ** exponent;
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return nice * 10 ** exponent;
}

export default function ErrorChart({
  series,
  slo = null,
  unit = "pct",
  format,
  minutes,
  windowStart,
  breach,
  markers = [],
  height = 300,
  yMax,
  playhead,
  selectedMarker,
  onMarkerClick,
  ariaLabel,
}: Props) {
  const [wrapRef, width] = useWidth();
  const uid = useId().replace(/:/g, "");
  const [hover, setHover] = useState<number | null>(null);

  const plotW = Math.max(0, width - MARGIN.left - MARGIN.right);
  const plotH = height - MARGIN.top - MARGIN.bottom;
  const last = Math.max(1, minutes - 1);

  const top = useMemo(() => {
    if (yMax) return yMax;
    const peak = Math.max(slo ? slo * 1.2 : 0, ...series.flatMap((s) => s.values));
    return unit === "pct" ? niceCeil(peak, 0.1) : niceNumberCeil(peak);
  }, [series, slo, yMax, unit]);

  const x = useCallback((t: number) => MARGIN.left + (t / last) * plotW, [last, plotW]);
  const y = useCallback((v: number) => MARGIN.top + plotH - (Math.min(v, top) / top) * plotH, [plotH, top]);

  const valueText = useCallback((v: number) => (format ? format(v) : pct(v)), [format]);
  const tickText = useCallback((v: number) => (unit === "pct" ? `${Math.round(v * 100)}%` : valueText(v)), [unit, valueText]);

  const yTicks = useMemo(() => {
    const step = unit === "number" ? top / 4 : top <= 0.5 ? 0.1 : top <= 1 ? 0.2 : 0.25;
    const ticks: number[] = [];
    for (let v = 0; v <= top + 1e-9; v += step) ticks.push(Number(v.toFixed(4)));
    return ticks;
  }, [top, unit]);

  const xTicks = useMemo(() => {
    // Widen the step on narrow charts so neighbouring labels never touch.
    const pxPerMin = last > 0 ? plotW / last : 0;
    let every = minutes > 90 ? 20 : 10;
    while (pxPerMin > 0 && every * pxPerMin < 52 && every < 60) every *= 2;
    const ticks: number[] = [];
    for (let t = 0; t < minutes; t += every) ticks.push(t);
    if (ticks[ticks.length - 1] !== last) {
      // Keep the final label from colliding with the one before it on narrow charts.
      const pxPerMinute = last > 0 ? plotW / last : 0;
      if (ticks.length > 1 && (last - ticks[ticks.length - 1]) * pxPerMinute < 44) ticks.pop();
      ticks.push(last);
    }
    return ticks;
  }, [minutes, last, plotW]);

  const rows = useMemo(() => markerRows(markers, plotW / last), [markers, plotW, last]);

  const onMove = (event: MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const t = Math.round(((event.clientX - rect.left - MARGIN.left) / plotW) * last);
    setHover(t < 0 || t > last ? null : t);
  };

  const onMarkerKey = (event: KeyboardEvent<SVGGElement>, id: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onMarkerClick?.(id);
    }
  };

  const linePath = (values: readonly number[]) => values.map((v, t) => `${t === 0 ? "M" : "L"} ${x(t).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const areaPath = (values: readonly number[]) => `${linePath(values)} L ${x(values.length - 1).toFixed(1)},${y(0)} L ${x(0).toFixed(1)},${y(0)} Z`;
  const morph = (d: string): CSSProperties => ({ d: `path("${d}")`, transition: "d 0.7s cubic-bezier(0.22,0.61,0.36,1), stroke 0.4s" }) as CSSProperties;

  const hoverX = hover === null ? 0 : x(hover);
  const tooltipLeft = hover !== null && hoverX > width * 0.62 ? hoverX - 168 : hoverX + 12;

  return (
    <div ref={wrapRef} className="relative w-full select-none" style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={ariaLabel} onMouseMove={onMove} onMouseLeave={() => setHover(null)} className="block overflow-visible">
          <defs>
            <clipPath id={`reveal-${uid}`}>
              <rect
                x={MARGIN.left}
                y={0}
                width={plotW}
                height={height}
                className="animate-grow-x"
                style={{ transformBox: "fill-box", transformOrigin: "left center" }}
              />
            </clipPath>
            {series.map((s) => (
              <linearGradient key={s.id} id={`fill-${uid}-${s.id}`} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity="0.28" />
                <stop offset="100%" stopColor={s.color} stopOpacity="0" />
              </linearGradient>
            ))}
          </defs>

          {yTicks.map((v) => (
            <g key={v}>
              <line x1={MARGIN.left} x2={width - MARGIN.right} y1={y(v)} y2={y(v)} stroke={v === 0 ? "#333539" : "#1a1c22"} strokeWidth={1} />
              <text x={MARGIN.left - 8} y={y(v) + 3} textAnchor="end" fill="#869397" fontFamily="JetBrains Mono Variable, monospace" fontSize={10}>
                {tickText(v)}
              </text>
            </g>
          ))}

          {xTicks.map((t) => (
            <text key={t} x={x(t)} y={height - 8} textAnchor={t === last ? "end" : t === 0 ? "start" : "middle"} fill="#869397" fontFamily="JetBrains Mono Variable, monospace" fontSize={10}>
              {minuteLabel(windowStart, t)}
            </text>
          ))}

          {breach && (
            <g>
              <rect x={x(breach.start)} y={MARGIN.top} width={Math.max(0, x(breach.end) - x(breach.start))} height={plotH} fill="#ffb4ab" fillOpacity={0.06} />
              <line x1={x(breach.start)} x2={x(breach.start)} y1={MARGIN.top} y2={MARGIN.top + plotH} stroke="#ffb4ab" strokeOpacity={0.4} strokeDasharray="3 3" />
              <line x1={x(breach.end)} x2={x(breach.end)} y1={MARGIN.top} y2={MARGIN.top + plotH} stroke="#4edea3" strokeOpacity={0.4} strokeDasharray="3 3" />
            </g>
          )}

          <g clipPath={`url(#reveal-${uid})`}>
            {series.map((s) =>
              s.area ? <path key={`${s.id}-area`} style={morph(areaPath(s.values))} d={areaPath(s.values)} fill={`url(#fill-${uid}-${s.id})`} opacity={s.opacity ?? 1} /> : null,
            )}
            {series.map((s) => (
              <path
                key={s.id}
                style={morph(linePath(s.values))}
                d={linePath(s.values)}
                fill="none"
                stroke={s.color}
                strokeWidth={s.width ?? 2.2}
                strokeDasharray={s.dashed ? "5 3" : undefined}
                strokeLinejoin="round"
                strokeLinecap="round"
                opacity={s.opacity ?? 1}
              />
            ))}
          </g>

          {slo !== null && (
            <g>
              <line x1={MARGIN.left} x2={width - MARGIN.right} y1={y(slo)} y2={y(slo)} stroke="#ffb95f" strokeWidth={1} strokeDasharray="4 4" />
              <text x={width - MARGIN.right - 4} y={y(slo) - 5} textAnchor="end" fill="#ffb95f" fontFamily="JetBrains Mono Variable, monospace" fontSize={9}>
                SLO {pct(slo, 0)}
              </text>
            </g>
          )}

          {markers.map((m) => {
            const color = CLASS_COLOR[m.cls];
            const row = rows.get(m.id) ?? 0;
            const labelY = 10 + row * 11;
            const selected = selectedMarker === m.id;
            return (
              <g
                key={m.id}
                role={onMarkerClick ? "button" : undefined}
                tabIndex={onMarkerClick ? 0 : undefined}
                aria-label={`${m.id}: ${m.label}`}
                className={onMarkerClick ? "cursor-pointer outline-none" : undefined}
                onClick={() => onMarkerClick?.(m.id)}
                onKeyDown={(event) => onMarkerKey(event, m.id)}
              >
                <title>{`${m.id} · ${minuteLabel(windowStart, m.t)} · ${m.label}`}</title>
                <line x1={x(m.t)} x2={x(m.t)} y1={labelY + 4} y2={MARGIN.top + plotH} stroke={color} strokeOpacity={selected ? 0.9 : 0.35} strokeDasharray="2 3" />
                <rect x={x(m.t) - 4} y={labelY - 4} width={8} height={8} transform={`rotate(45 ${x(m.t)} ${labelY})`} fill={color} stroke="#08090c" strokeWidth={selected ? 0 : 1} className={selected ? "drop-shadow-[0_0_6px_currentColor]" : undefined} style={selected ? { color } : undefined} />
                <text x={x(m.t) + 8} y={labelY + 3} fill={color} fontFamily="JetBrains Mono Variable, monospace" fontSize={9} fontWeight={selected ? 700 : 500}>
                  {m.id}
                </text>
                {/* generous hit area */}
                <rect x={x(m.t) - 8} y={0} width={16} height={MARGIN.top + plotH} fill="transparent" />
              </g>
            );
          })}

          {hover !== null && (
            <g pointerEvents="none">
              <line x1={hoverX} x2={hoverX} y1={MARGIN.top} y2={MARGIN.top + plotH} stroke="#ffffff" strokeOpacity={0.25} />
              {series.map((s) => (
                <circle key={s.id} cx={hoverX} cy={y(s.values[hover] ?? 0)} r={3.5} fill={s.color} stroke="#08090c" strokeWidth={1.5} />
              ))}
            </g>
          )}

          {playhead !== null && playhead !== undefined && (
            <g pointerEvents="none">
              <line x1={x(playhead)} x2={x(playhead)} y1={MARGIN.top - 6} y2={MARGIN.top + plotH} stroke="#4cd7f6" strokeWidth={1.5} style={{ filter: "drop-shadow(0 0 4px #4cd7f6)" }} />
              {series.map((s) => (
                <circle key={s.id} cx={x(playhead)} cy={y(s.values[Math.min(s.values.length - 1, Math.round(playhead))] ?? 0)} r={4.5} fill={s.color} stroke="#08090c" strokeWidth={2} />
              ))}
            </g>
          )}
        </svg>
      )}

      {hover !== null && width > 0 && (
        <div
          className="pointer-events-none absolute top-1 z-10 w-40 rounded border border-white/15 bg-[#08090c]/95 p-space-md font-mono-data-compact shadow-lg"
          style={{ left: Math.max(0, tooltipLeft) }}
        >
          <div className="mb-1 text-outline">{minuteLabel(windowStart, hover)} UTC</div>
          {series.map((s) => (
            <div key={s.id} className="flex items-center justify-between gap-space-md">
              <span className="flex items-center gap-1 truncate text-on-surface-variant">
                <span className="inline-block h-0.5 w-2.5" style={{ background: s.color }} />
                {s.label}
              </span>
              <span className="tabular-nums text-on-surface">{valueText(s.values[hover] ?? 0)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
