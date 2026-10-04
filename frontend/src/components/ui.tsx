// Shared building blocks, styled with the Stitch tokens (see tailwind.config.js).
import type { ButtonHTMLAttributes, ReactNode } from "react";

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

export function Icon({ name, className }: { name: string; className?: string }) {
  return (
    <span aria-hidden="true" className={cx("material-symbols-outlined select-none", className)}>
      {name}
    </span>
  );
}

export type Tone = "primary" | "secondary" | "tertiary" | "error" | "muted";

export const TONE_TEXT: Record<Tone, string> = {
  primary: "text-primary",
  secondary: "text-secondary",
  tertiary: "text-tertiary",
  error: "text-error",
  muted: "text-outline",
};

const BADGE: Record<Tone, string> = {
  primary: "bg-primary/15 text-primary border-primary/40",
  secondary: "bg-secondary/15 text-secondary border-secondary/40",
  tertiary: "bg-tertiary/15 text-tertiary border-tertiary/40",
  error: "bg-error-container/60 text-on-error-container border-error/40",
  muted: "bg-outline/15 text-on-surface-variant border-outline/30",
};

export function Badge({ tone = "muted", children, className, title }: { tone?: Tone; children: ReactNode; className?: string; title?: string }) {
  return (
    <span
      title={title}
      className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 font-mono-label-caps uppercase", BADGE[tone], className)}
    >
      {children}
    </span>
  );
}

export function Panel({ children, className, glow }: { children: ReactNode; className?: string; glow?: Tone }) {
  const glowClass =
    glow === "secondary"
      ? "border-secondary/50 shadow-[0_0_25px_rgba(78,222,163,0.15)]"
      : glow === "primary"
        ? "border-primary/50 shadow-[0_0_30px_rgba(76,215,246,0.18)]"
        : glow === "error"
          ? "border-error/50 shadow-[0_0_25px_rgba(255,180,171,0.12)]"
          : glow === "tertiary"
            ? "border-tertiary/50 shadow-[0_0_25px_rgba(255,185,95,0.12)]"
            : "";
  return <section className={cx("glass p-space-md", glowClass, className)}>{children}</section>;
}

export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("font-mono-label-caps uppercase tracking-wider text-outline", className)}>{children}</span>;
}

export function ViewHeader({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="glass flex flex-col justify-between gap-space-md p-space-md md:flex-row md:items-center">
      <div className="min-w-0">
        <h2 className="font-headline-lg text-headline-lg text-on-surface">{title}</h2>
        {subtitle && <p className="font-body-sm text-body-sm text-on-surface-variant">{subtitle}</p>}
      </div>
      {children && <div className="flex shrink-0 flex-wrap items-center gap-space-sm">{children}</div>}
    </div>
  );
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON: Record<ButtonVariant, string> = {
  primary:
    "bg-primary text-on-primary font-semibold shadow-[0_0_20px_rgba(76,215,246,0.35)] hover:bg-primary-fixed-dim hover:shadow-[0_0_26px_rgba(76,215,246,0.5)] disabled:opacity-40 disabled:shadow-none",
  secondary: "bg-[#161920]/80 text-on-surface border border-white/15 hover:bg-[#1f232c] hover:border-white/25 disabled:opacity-40",
  ghost: "text-on-surface-variant hover:text-on-surface hover:bg-white/5 disabled:opacity-40",
  danger: "bg-error-container/70 text-on-error-container border border-error/50 hover:bg-error-container disabled:opacity-40",
};

export function Button({
  variant = "secondary",
  icon,
  children,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; icon?: string }) {
  return (
    <button
      type="button"
      {...rest}
      className={cx(
        "inline-flex items-center justify-center gap-space-md rounded px-space-xl py-1.5 font-mono-data transition-all active:scale-[0.98]",
        BUTTON[variant],
        className,
      )}
    >
      {icon && <Icon name={icon} className="text-[16px]" />}
      {children}
    </button>
  );
}

/** A horizontal meter whose fill animates when `value` changes. */
export function Meter({ value, tone = "primary", className }: { value: number; tone?: Tone; className?: string }) {
  const fill: Record<Tone, string> = {
    primary: "bg-primary",
    secondary: "bg-secondary",
    tertiary: "bg-tertiary",
    error: "bg-error",
    muted: "bg-outline",
  };
  return (
    <div
      role="meter"
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={Number(value.toFixed(2))}
      className={cx("h-1.5 w-full overflow-hidden rounded bg-white/10", className)}
    >
      <div className={cx("h-full rounded transition-[width] duration-700 ease-out", fill[tone])} style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
    </div>
  );
}

export function Kpi({
  label,
  value,
  unit,
  sub,
  tone = "primary",
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  sub?: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="glass flex flex-col gap-space-xs p-space-md transition-colors hover:border-white/25">
      <Label>{label}</Label>
      <div className="flex items-baseline gap-space-md">
        <span className={cx("font-mono-metric-lg text-[28px] font-bold tabular-nums", TONE_TEXT[tone])}>{value}</span>
        {unit && <span className="font-mono-data text-on-surface-variant">{unit}</span>}
      </div>
      {sub && <span className="font-mono-data-compact text-on-surface-variant">{sub}</span>}
    </div>
  );
}

/** Shown in place of a view whose data the agent has not produced yet. */
export function Pending({ title, hint, rows = 3 }: { title: string; hint?: string; rows?: number }) {
  return (
    <div className="glass animate-fade-in flex flex-col gap-space-lg p-space-xl" role="status" aria-live="polite">
      <div className="flex items-center gap-space-md">
        <Icon name="hourglass_top" className="animate-pulse text-[20px] text-primary" />
        <div>
          <div className="font-headline-sm text-on-surface">{title}</div>
          {hint && <div className="font-body-sm text-on-surface-variant">{hint}</div>}
        </div>
      </div>
      <div className="flex flex-col gap-space-md">
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="skeleton h-9" style={{ width: `${92 - i * 14}%` }} />
        ))}
      </div>
    </div>
  );
}

export function Notice({ tone, icon, title, children, action }: { tone: Tone; icon: string; title: string; children?: ReactNode; action?: ReactNode }) {
  const border: Record<Tone, string> = {
    primary: "border-primary/40 bg-primary/10",
    secondary: "border-secondary/40 bg-secondary-container/15",
    tertiary: "border-tertiary/40 bg-tertiary-container/15",
    error: "border-error/50 bg-error-container/30",
    muted: "border-white/10 bg-white/5",
  };
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cx("animate-fade-up flex items-start gap-space-lg rounded border p-space-lg", border[tone])}>
      <Icon name={icon} className={cx("mt-0.5 text-[20px]", TONE_TEXT[tone])} />
      <div className="min-w-0 flex-1">
        <div className={cx("font-headline-sm", TONE_TEXT[tone])}>{title}</div>
        {children && <div className="mt-0.5 font-body-sm text-on-surface-variant">{children}</div>}
      </div>
      {action}
    </div>
  );
}
