#!/usr/bin/env node
// WCAG AA contrast gate for the token pairs EZTracker actually renders (§9).
// Reads src/styles/tokens.css (the single source of truth) and fails if any pair regresses.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, "../src/styles/tokens.css"), "utf8");

function block(selector) {
  const i = css.indexOf(selector);
  if (i < 0) throw new Error(`selector not found: ${selector}`);
  const body = css.slice(css.indexOf("{", i) + 1, css.indexOf("}", i));
  return Object.fromEntries([...body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));
}
const themes = { light: block(":root {"), dark: block(":root[data-theme=\"dark\"]") };

const lum = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

// [foreground, background, minimum, why]
const TEXT = 4.5, UI = 3.0;
const pairs = [];
for (const bg of ["bg", "surface", "surface-2"]) {
  pairs.push(["text", bg, TEXT, "body text"], ["text-muted", bg, TEXT, "secondary text"],
    ["text-faint", bg, TEXT, "meta / timestamps (small)"],
    ["danger-text", bg, TEXT, "overdue label"], ["warning-text", bg, TEXT, "due-soon label"],
    ["success-text", bg, TEXT, "submitted label"], ["info-text", bg, TEXT, "parsed-date hint"],
    ["accent-text", bg, TEXT, "links / selected"], ["primary", bg, UI, "primary UI fill & focus base"],
    ["danger", bg, UI, "overdue icon / dot"], ["warning", bg, UI, "due-soon icon / dot"],
    ["success", bg, UI, "submitted check"], ["accent", bg, UI, "accent UI"]);
}
pairs.push(["primary-fg", "primary", TEXT, "text on primary button"]);

let failed = 0;
for (const [name, t] of Object.entries(themes)) {
  console.log(`\n${name}`);
  for (const [fg, bg, min, why] of pairs) {
    if (!t[fg] || !t[bg]) { console.log(`  ✗ missing token ${fg} or ${bg}`); failed++; continue; }
    const r = ratio(t[fg], t[bg]);
    const ok = r >= min;
    if (!ok) failed++;
    console.log(`  ${ok ? "✓" : "✗"} ${fg.padEnd(13)} on ${bg.padEnd(9)} ${r.toFixed(2).padStart(5)} ≥ ${min}  ${why}`);
  }
}
if (failed) { console.error(`\n${failed} contrast pair(s) below WCAG AA`); process.exit(1); }
console.log("\nall pairs pass WCAG AA");
