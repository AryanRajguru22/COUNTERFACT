// The master timeline: events on a minute axis (labels laned so neighbours never overprint), the SLO breach underlay,
// and aligned metric streams underneath. Click or Enter/Space on a node selects the event.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { EVENT_CLASS_LABEL, type BreachWindow, type EventClass } from "../../lib/derive";
import { minuteLabel } from "../../lib/format";
import type { Event } from "../../types";
import { CLASS_COLOR } from "./ErrorChart";

export interface Stream {
  id: string;
  label: string;
  values: readonly number[];
  color: string;
  max: number;
  format: (v: number) => string;
}

interface Props {
  events: readonly { event: Event; cls: EventClass; label: string }[];
  minutes: number;
  windowStart: string;
  breach: BreachWindow | null;
  streams: readonly Stream[];
  selected: string | null;
  onSelect: (id: string) => void;
}

const M = { left: 24, right: 24 };
const LANE = 26;
const LANES = 4;
const STREAM_H = 38;

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

const labelWidth = (text: string) => text.length * 6.3 + 22;

export default function TimelineStrip({ events, minutes, windowStart, breach, streams, selected, onSelect }: Props) {
  const [wrapRef, measured] = useWidth();
  const width = Math.max(measured, 760);
  const plotW = width - M.left - M.right;
  const last = Math.max(1, minutes - 1);
  const x = (t: number) => M.left + (t / last) * plotW;

  // Greedy lane assignment: alternate above/below the axis, first lane where the label fits.
  const placed = useMemo(() => {
    const ends: Record<string, number[]> = { up: Array(LANES).fill(-Infinity), down: Array(LANES).fill(-Infinity) };
    return [...events]
      .sort((a, b) => a.event.t - b.event.t || a.event.id.localeCompare(b.event.id))
      .map((item, i) => {
        const left = M.left + (item.event.t / last) * plotW - 8;
        const width = labelWidth(item.label);
        const order = i % 2 === 0 ? (["up", "down"] as const) : (["down", "up"] as const);
        for (const side of order) {
          const lane = ends[side].findIndex((end) => left >= end + 6);
          if (lane !== -1) {
            ends[side][lane] = left + width;
            return { ...item, side, lane, width };
          }
        }
        const side = order[0];
        const lane = LANES - 1;
        ends[side][lane] = left + width;
        return { ...item, side, lane, width };
      });
  }, [events, last, plotW]);

  const axisY = LANE * LANES + 18;
  const height = axisY * 2 + 22 + streams.length * (STREAM_H + 8);
  const ticks = useMemo(() => Array.from({ length: Math.floor(last / 10) + 1 }, (_, i) => i * 10), [last]);

  const onKey = (event: KeyboardEvent<SVGGElement>, id: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(id);
    }
  };

  return (
    <div ref={wrapRef} className="w-full overflow-x-auto pb-1">
      <svg width={width} height={height} role="group" aria-label="Incident timeline" className="block select-none overflow-visible">
        {breach && (
          <g>
            <rect x={x(breach.start)} y={14} width={x(breach.end) - x(breach.start)} height={axisY * 2 - 10} rx={4} fill="#93000a" fillOpacity={0.16} />
            <text x={x(breach.start) + 8} y={26} fill="#ffb4ab" fontFamily="JetBrains Mono Variable, monospace" fontSize={10} fontWeight={600}>
              SLO BREACH · {breach.minutes} min
            </text>
          </g>
        )}

        <line x1={M.left} x2={width - M.right} y1={axisY} y2={axisY} stroke="#333539" strokeWidth={2} />
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={axisY - 5} y2={axisY + 5} stroke="#869397" />
            <text x={x(t)} y={axisY + 20} textAnchor="middle" fill="#869397" fontFamily="JetBrains Mono Variable, monospace" fontSize={10}>
              {minuteLabel(windowStart, t)}
            </text>
          </g>
        ))}

        {placed.map(({ event, cls, label, side, lane, width: w }) => {
          const color = CLASS_COLOR[cls];
          const cx = x(event.t);
          const sign = side === "up" ? -1 : 1;
          const labelY = axisY + sign * (LANE * (lane + 1) - 4) - (side === "up" ? 6 : -6);
          const isSelected = selected === event.id;
          const boxX = cx - 8;
          return (
            <g
              key={event.id}
              role="button"
              tabIndex={0}
              aria-label={`${event.id} ${EVENT_CLASS_LABEL[cls]} at ${minuteLabel(windowStart, event.t)}: ${event.summary}`}
              aria-pressed={isSelected}
              className="cursor-pointer outline-none"
              onClick={() => onSelect(event.id)}
              onKeyDown={(e) => onKey(e, event.id)}
            >
              <title>{`${event.id} · ${minuteLabel(windowStart, event.t)} UTC · ${event.summary}`}</title>
              <line x1={cx} x2={cx} y1={axisY} y2={labelY + (side === "up" ? 8 : -8)} stroke={color} strokeOpacity={isSelected ? 0.9 : 0.4} />
              <rect
                x={boxX}
                y={labelY - 10}
                width={w}
                height={20}
                rx={3}
                fill={isSelected ? "#282a2e" : "#1e2024"}
                stroke={isSelected ? color : "transparent"}
                strokeWidth={1}
                opacity={cls === "decoy" && !isSelected ? 0.75 : 1}
                className="transition-all"
              />
              <circle cx={boxX + 8} cy={labelY} r={3} fill={color} />
              <text x={boxX + 16} y={labelY + 3.5} fill={cls === "decoy" ? "#869397" : "#e2e2e8"} fontFamily="JetBrains Mono Variable, monospace" fontSize={10.5} fontWeight={cls === "cause" ? 600 : 400}>
                {label}
              </text>
              {isSelected && <circle cx={cx} cy={axisY} r={11} fill="none" stroke={color} strokeOpacity={0.7} className="animate-pulse-ring" />}
              <circle cx={cx} cy={axisY} r={cls === "cause" ? 7 : 5.5} fill={color} stroke="#08090c" strokeWidth={3} className="transition-transform hover:scale-125" style={{ transformBox: "fill-box", transformOrigin: "center" }} />
              {event.state_change && <rect x={cx - 2} y={axisY - 2} width={4} height={4} fill="#08090c" transform={`rotate(45 ${cx} ${axisY})`} />}
              <rect x={cx - 9} y={axisY - 12} width={18} height={24} fill="transparent" />
            </g>
          );
        })}

        {streams.map((stream, i) => {
          const top = axisY * 2 + 22 + i * (STREAM_H + 8);
          const y = (v: number) => top + STREAM_H - (Math.min(v, stream.max) / stream.max) * STREAM_H;
          const d = stream.values.map((v, t) => `${t === 0 ? "M" : "L"} ${x(t).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
          const peak = Math.max(...stream.values);
          return (
            <g key={stream.id}>
              <rect x={M.left} y={top} width={plotW} height={STREAM_H} fill="#08090c" fillOpacity={0.5} rx={3} />
              <path d={`${d} L ${x(stream.values.length - 1)},${top + STREAM_H} L ${x(0)},${top + STREAM_H} Z`} fill={stream.color} fillOpacity={0.12} />
              <path d={d} fill="none" stroke={stream.color} strokeWidth={1.6} strokeLinejoin="round" />
              <text x={M.left + 6} y={top + 11} fill="#869397" fontFamily="JetBrains Mono Variable, monospace" fontSize={9.5}>
                {stream.label}
              </text>
              <text x={width - M.right - 6} y={top + 11} textAnchor="end" fill={stream.color} fontFamily="JetBrains Mono Variable, monospace" fontSize={9.5}>
                peak {stream.format(peak)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
