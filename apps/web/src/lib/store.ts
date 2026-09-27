import { create } from "zustand";

type Theme = "light" | "dark" | "system";
type Density = "comfortable" | "compact";

function read<T extends string>(key: string, fallback: T, allowed: readonly T[]): T {
  try {
    const v = localStorage.getItem(key) as T | null;
    return v && allowed.includes(v) ? v : fallback;
  } catch {
    return fallback;
  }
}
function write(key: string, v: string) {
  try {
    localStorage.setItem(key, v);
  } catch {
    /* storage unavailable — keep in memory */
  }
}

export interface Toast {
  id: number;
  title: string;
  description?: string;
  tone?: "default" | "danger";
  action?: { label: string; onClick: () => void };
  duration?: number;
}

interface UIState {
  drawerItemId: string | null;
  openItem: (id: string | null) => void;
  paletteOpen: boolean;
  setPaletteOpen: (v: boolean) => void;
  moveTargetId: string | null; // item whose "Move to…" dialog is open
  setMoveTarget: (id: string | null) => void;
  railCollapsed: boolean;
  toggleRail: () => void;

  theme: Theme;
  setTheme: (t: Theme) => void;
  grain: boolean;
  setGrain: (v: boolean) => void;
  density: Density;
  setDensity: (d: Density) => void;
  hideInfo: boolean;
  setHideInfo: (v: boolean) => void;
  boardOrder: "due" | "alpha";
  setBoardOrder: (v: "due" | "alpha") => void;

  toasts: Toast[];
  toast: (t: Omit<Toast, "id">) => number;
  dismissToast: (id: number) => void;
  lastUndo: (() => void) | null;
  setLastUndo: (fn: (() => void) | null) => void;
}

export function applyTheme(t: Theme) {
  const el = document.documentElement;
  if (t === "system") delete el.dataset.theme;
  else el.dataset.theme = t;
}

let toastSeq = 0;

export const useUI = create<UIState>((set) => ({
  drawerItemId: null,
  openItem: (id) => set({ drawerItemId: id }),
  paletteOpen: false,
  setPaletteOpen: (v) => set({ paletteOpen: v }),
  moveTargetId: null,
  setMoveTarget: (id) => set({ moveTargetId: id }),
  railCollapsed: read("ez.rail", "open", ["open", "collapsed"] as const) === "collapsed",
  toggleRail: () =>
    set((s) => {
      write("ez.rail", s.railCollapsed ? "open" : "collapsed");
      return { railCollapsed: !s.railCollapsed };
    }),

  theme: read("ez.theme", "system", ["light", "dark", "system"] as const),
  setTheme: (t) => {
    write("ez.theme", t);
    applyTheme(t);
    set({ theme: t });
  },
  grain: read("ez.grain", "on", ["on", "off"] as const) === "on",
  setGrain: (v) => {
    write("ez.grain", v ? "on" : "off");
    set({ grain: v });
  },
  density: read("ez.density", "comfortable", ["comfortable", "compact"] as const),
  setDensity: (d) => {
    write("ez.density", d);
    set({ density: d });
  },
  hideInfo: read("ez.hideInfo", "off", ["on", "off"] as const) === "on",
  setHideInfo: (v) => {
    write("ez.hideInfo", v ? "on" : "off");
    set({ hideInfo: v });
  },
  boardOrder: read("ez.boardOrder", "due", ["due", "alpha"] as const),
  setBoardOrder: (v) => {
    write("ez.boardOrder", v);
    set({ boardOrder: v });
  },

  toasts: [],
  toast: (t) => {
    const id = ++toastSeq;
    set((s) => ({ toasts: [...s.toasts.slice(-2), { ...t, id }] }));
    return id;
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  lastUndo: null,
  setLastUndo: (fn) => set({ lastUndo: fn }),
}));
