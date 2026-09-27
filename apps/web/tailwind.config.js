/** Tailwind reads colors from CSS variables in src/styles/tokens.css, so both themes share one class set. */
const v = (name) => `var(--${name})`;
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: v("bg"), surface: v("surface"), "surface-2": v("surface-2"), border: v("border"),
        text: v("text"), muted: v("text-muted"), faint: v("text-faint"),
        primary: v("primary"), "primary-fg": v("primary-fg"),
        accent: v("accent"), "accent-text": v("accent-text"),
        danger: v("danger"), "danger-text": v("danger-text"),
        warning: v("warning"), "warning-text": v("warning-text"),
        success: v("success"), "success-text": v("success-text"),
        info: v("info"), "info-text": v("info-text"),
      },
      fontFamily: { display: v("font-display"), ui: v("font-ui") },
      fontSize: {
        meta: ["0.78rem", { lineHeight: "1.5" }],
        small: ["0.85rem", { lineHeight: "1.55" }],
        body: ["0.9375rem", { lineHeight: "1.6" }],
        emph: ["1.0625rem", { lineHeight: "1.55" }],
        h3: ["1.25rem", { lineHeight: "1.3" }],
        h2: ["1.7rem", { lineHeight: "1.2" }],
        h1: ["2.4rem", { lineHeight: "1.15" }],
      },
      borderRadius: { card: "10px", col: "14px" },
      boxShadow: { card: v("shadow-card"), lift: v("shadow-lift"), focus: v("focus"), hairline: v("elev-hairline") },
      transitionTimingFunction: { ez: v("ease") },
      transitionDuration: { press: "120ms", toggle: "180ms", move: "240ms" },
      letterSpacing: { micro: "0.06em" },
    },
  },
  plugins: [],
};
