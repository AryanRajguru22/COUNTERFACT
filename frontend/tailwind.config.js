// Design tokens come from the Stitch project "COUNTERFACT: Forensic Incident Lab" (Visual Forensic Motion Workspace).
import plugin from "tailwindcss/plugin";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "on-tertiary-container": "#563400",
        error: "#ffb4ab",
        "outline-variant": "#3d494c",
        primary: "#4cd7f6",
        "surface-container-high": "#282a2e",
        "secondary-fixed-dim": "#4edea3",
        "on-background": "#e2e2e8",
        "surface-container-highest": "#333539",
        "inverse-on-surface": "#2f3035",
        tertiary: "#ffb95f",
        "on-secondary-fixed": "#002113",
        "on-error": "#690005",
        "error-container": "#93000a",
        "on-primary-fixed": "#001f26",
        "tertiary-fixed": "#ffddb8",
        "surface-variant": "#333539",
        "on-surface": "#e2e2e8",
        background: "#0c0e12",
        "inverse-primary": "#00687a",
        "secondary-fixed": "#6ffbbe",
        "on-primary-container": "#00424f",
        "primary-fixed-dim": "#4cd7f6",
        "on-secondary-fixed-variant": "#005236",
        "on-primary-fixed-variant": "#004e5c",
        secondary: "#4edea3",
        "surface-dim": "#111317",
        "on-surface-variant": "#bcc9cd",
        surface: "#111317",
        "surface-bright": "#37393e",
        "on-tertiary-fixed-variant": "#653e00",
        "on-primary": "#003640",
        "on-tertiary": "#472a00",
        "surface-container-lowest": "#08090c",
        "surface-container": "#1e2024",
        "surface-container-low": "#14161a",
        "surface-tint": "#4cd7f6",
        outline: "#869397",
        "secondary-container": "#00a572",
        "primary-fixed": "#acedff",
        "on-error-container": "#ffdad6",
        "on-secondary-container": "#00311f",
        "on-tertiary-fixed": "#2a1700",
        "primary-container": "#06b6d4",
        "inverse-surface": "#e2e2e8",
        "tertiary-fixed-dim": "#ffb95f",
        "on-secondary": "#003824",
        "tertiary-container": "#e79400",
      },
      borderRadius: { DEFAULT: "0.125rem", lg: "0.25rem", xl: "0.5rem", full: "0.75rem" },
      spacing: {
        "gutter-mobile": "0.25rem",
        gutter: "0.5rem",
        "space-xs": "0.125rem",
        "space-md": "0.5rem",
        "margin-mobile": "0.5rem",
        "space-lg": "0.75rem",
        margin: "0.75rem",
        "space-sm": "0.25rem",
        "space-xl": "1rem",
      },
      fontFamily: {
        "headline-lg": ["Inter Variable", "Inter", "system-ui", "sans-serif"],
        "body-md": ["Inter Variable", "Inter", "system-ui", "sans-serif"],
        "headline-sm": ["Inter Variable", "Inter", "system-ui", "sans-serif"],
        "headline-xl": ["Inter Variable", "Inter", "system-ui", "sans-serif"],
        "body-sm": ["Inter Variable", "Inter", "system-ui", "sans-serif"],
        "mono-metric-lg": ["JetBrains Mono Variable", "JetBrains Mono", "ui-monospace", "monospace"],
        "mono-data-compact": ["JetBrains Mono Variable", "JetBrains Mono", "ui-monospace", "monospace"],
        "mono-data": ["JetBrains Mono Variable", "JetBrains Mono", "ui-monospace", "monospace"],
        "mono-label-caps": ["JetBrains Mono Variable", "JetBrains Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        "headline-lg": ["18px", { lineHeight: "24px", letterSpacing: "-0.015em", fontWeight: "600" }],
        "body-md": ["13px", { lineHeight: "18px", fontWeight: "400" }],
        "mono-metric-lg": ["20px", { lineHeight: "24px", letterSpacing: "-0.02em", fontWeight: "600" }],
        "mono-data-compact": ["11px", { lineHeight: "14px", fontWeight: "400" }],
        "headline-sm": ["14px", { lineHeight: "20px", letterSpacing: "-0.01em", fontWeight: "600" }],
        "headline-xl": ["24px", { lineHeight: "32px", letterSpacing: "-0.02em", fontWeight: "600" }],
        "mono-data": ["12px", { lineHeight: "16px", fontWeight: "400" }],
        "mono-label-caps": ["10px", { lineHeight: "12px", letterSpacing: "0.06em", fontWeight: "600" }],
        "body-sm": ["12px", { lineHeight: "16px", fontWeight: "400" }],
      },
      keyframes: {
        "fade-up": { "0%": { opacity: "0", transform: "translateY(8px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        "fade-in": { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        shimmer: { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
        "pulse-ring": { "0%": { boxShadow: "0 0 0 0 rgba(76,215,246,0.45)" }, "100%": { boxShadow: "0 0 0 10px rgba(76,215,246,0)" } },
        "draw-path": { "0%": { strokeDashoffset: "var(--len, 1200)" }, "100%": { strokeDashoffset: "0" } },
        "grow-x": { "0%": { transform: "scaleX(0)" }, "100%": { transform: "scaleX(1)" } },
      },
      animation: {
        "fade-up": "fade-up 0.35s ease-out both",
        "fade-in": "fade-in 0.3s ease-out both",
        shimmer: "shimmer 2.2s linear infinite",
        "pulse-ring": "pulse-ring 1.6s ease-out infinite",
        "grow-x": "grow-x 0.7s cubic-bezier(0.22, 0.61, 0.36, 1) both",
      },
    },
  },
  plugins: [
    // Stitch pairs `font-<token>` with `text-<token>`; make `font-<token>` carry the whole type token (size, leading,
    // tracking, weight) so one class is enough. Components sit below utilities, so `font-semibold` etc. still win.
    plugin(({ addComponents, theme }) => {
      const sizes = theme("fontSize");
      const families = theme("fontFamily");
      const tokens = {};
      for (const [name, value] of Object.entries(sizes)) {
        if (!(name in families)) continue;
        const [size, meta] = value;
        tokens[`.font-${name}`] = {
          fontFamily: families[name].join(", "),
          fontSize: size,
          ...(meta.lineHeight && { lineHeight: meta.lineHeight }),
          ...(meta.letterSpacing && { letterSpacing: meta.letterSpacing }),
          ...(meta.fontWeight && { fontWeight: meta.fontWeight }),
        };
      }
      addComponents(tokens);
    }),
  ],
};
