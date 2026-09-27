import { CalendarCheck, ChevronsLeft, ChevronsRight, Inbox, LayoutGrid, Library, Moon, Search, Settings, Sun, SunMoon } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Button, Kbd, Tip } from "@/components/ui/primitives";
import { CommandPalette } from "@/features/search/CommandPalette";
import { ItemDrawer } from "@/features/item/ItemDrawer";
import { MoveToDialog } from "@/features/board/MoveToDialog";
import { OfflineBanner, StaleBanner, SyncChip, SyncNowButton } from "@/features/sync/SyncChip";
import { backend } from "@/lib/backend";
import { APP_NAME } from "@/lib/brand";
import { cn } from "@/lib/cn";
import { isNeedsReview } from "@/lib/items";
import { useItems, useRealtime } from "@/lib/queries";
import { useUI } from "@/lib/store";

const TITLES: Record<string, string> = {
  "/today": "Today",
  "/board": "Board",
  "/review": "Needs Review",
  "/courses": "Courses",
  "/settings": "Settings",
  "/styleguide": "Styleguide",
};

function useOnline() {
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true), off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

function NavItem({ to, icon, label, badge, collapsed }: { to: string; icon: ReactNode; label: string; badge?: number; collapsed: boolean }) {
  const link = (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "relative flex h-10 items-center gap-3 rounded-lg px-3 text-body transition-colors duration-press",
          isActive ? "bg-surface text-text shadow-card" : "text-muted hover:bg-surface-2 hover:text-text",
          collapsed && "justify-center px-0",
        )
      }
    >
      {icon}
      {!collapsed && <span className="flex-1 truncate">{label}</span>}
      {collapsed && <span className="sr-only">{label}</span>}
      {!!badge && (
        <span
          aria-label={`${badge} to review`}
          className={cn(
            "grid h-5 min-w-5 place-items-center rounded-full bg-[color-mix(in_oklab,var(--accent)_18%,transparent)] px-1.5 text-meta font-semibold text-accent-text",
            collapsed && "absolute -right-1 -top-1",
          )}
        >
          {badge}
        </span>
      )}
    </NavLink>
  );
  return collapsed ? <Tip content={label} side="right">{link}</Tip> : link;
}

export function ThemeToggle() {
  const { theme, setTheme } = useUI();
  const next = theme === "system" ? "light" : theme === "light" ? "dark" : "system";
  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : SunMoon;
  return (
    <Tip content={`Theme: ${theme} (click for ${next})`}>
      <Button variant="ghost" size="icon" aria-label={`Theme: ${theme}. Switch to ${next}`} onClick={() => setTheme(next)}>
        <Icon size={18} strokeWidth={1.5} />
      </Button>
    </Tip>
  );
}

export function Shell() {
  useRealtime();
  const { railCollapsed, toggleRail, setPaletteOpen, grain } = useUI();
  const { data: items = [] } = useItems();
  const review = items.filter(isNeedsReview).length;
  const loc = useLocation();
  const online = useOnline();
  const title = TITLES[loc.pathname] ?? APP_NAME;

  useEffect(() => {
    document.title = `${title} · ${APP_NAME}`;
  }, [title]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPaletteOpen]);

  const nav = [
    { to: "/today", icon: <CalendarCheck size={18} strokeWidth={1.5} />, label: "Today" },
    { to: "/board", icon: <LayoutGrid size={18} strokeWidth={1.5} />, label: "Board" },
    { to: "/review", icon: <Inbox size={18} strokeWidth={1.5} />, label: "Needs Review", badge: review },
    { to: "/courses", icon: <Library size={18} strokeWidth={1.5} />, label: "Courses" },
    { to: "/settings", icon: <Settings size={18} strokeWidth={1.5} />, label: "Settings" },
  ];

  return (
    <div className={cn("flex min-h-dvh bg-bg", grain && "grain")}>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      {/* left rail (tablet/desktop) */}
      <aside
        className={cn(
          "sticky top-0 z-20 hidden h-dvh shrink-0 flex-col border-r border-border px-3 py-4 transition-[width] duration-move ease-ez md:flex",
          railCollapsed ? "w-16" : "w-[248px]",
        )}
      >
        <div className={cn("mb-6 flex items-center", railCollapsed ? "justify-center" : "justify-between px-2")}>
          {!railCollapsed && <span className="font-display text-[1.6rem] leading-none">{APP_NAME}</span>}
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={toggleRail} aria-label={railCollapsed ? "Expand sidebar" : "Collapse sidebar"}>
            {railCollapsed ? <ChevronsRight size={16} strokeWidth={1.5} /> : <ChevronsLeft size={16} strokeWidth={1.5} />}
          </Button>
        </div>
        <nav aria-label="Primary" className="flex flex-1 flex-col gap-1">
          {nav.map((n) => <NavItem key={n.to} {...n} collapsed={railCollapsed} />)}
        </nav>
        <SyncChip collapsed={railCollapsed} />
        {backend().mode === "demo" && !railCollapsed && (
          <p className="mt-2 px-3 text-meta text-faint">Demo data · no Supabase configured</p>
        )}
      </aside>

      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-2 border-b border-border bg-[color-mix(in_oklab,var(--bg)_88%,transparent)] px-4 backdrop-blur md:px-6">
          <span className="font-display text-[1.35rem] md:hidden">{APP_NAME}</span>
          <h1 className="hidden font-display text-h2 md:block">{title}</h1>
          <div className="flex-1" />
          <button
            onClick={() => setPaletteOpen(true)}
            className="flex h-10 items-center gap-2 rounded-lg border border-border bg-surface px-3 text-small text-faint hover:text-muted md:w-64"
            aria-label="Search and commands"
          >
            <Search size={16} strokeWidth={1.5} />
            <span className="hidden flex-1 text-left md:inline">Search items…</span>
            <span className="hidden md:inline"><Kbd>⌘K</Kbd></span>
          </button>
          <ThemeToggle />
          <SyncNowButton />
        </header>
        <OfflineBanner online={online} />
        <StaleBanner />
        <main id="main" className="min-w-0 flex-1 pb-24 md:pb-8">
          <h1 className="px-4 pt-4 font-display text-h2 md:hidden">{title}</h1>
          <Outlet />
        </main>
      </div>

      {/* bottom tab bar (phone) */}
      <nav aria-label="Primary" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] md:hidden">
        {nav.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            className={({ isActive }) => cn("relative flex h-14 flex-col items-center justify-center gap-0.5 text-meta", isActive ? "text-text" : "text-faint")}
          >
            {n.icon}
            <span className="truncate">{n.label === "Needs Review" ? "Review" : n.label}</span>
            {!!n.badge && <span className="absolute right-[22%] top-2 h-2 w-2 rounded-full bg-accent" aria-label={`${n.badge} to review`} />}
          </NavLink>
        ))}
      </nav>

      <ItemDrawer />
      <CommandPalette />
      <MoveToDialog />
    </div>
  );
}
