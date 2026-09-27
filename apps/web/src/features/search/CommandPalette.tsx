import * as DialogP from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { CalendarCheck, CheckCircle2, FolderInput, Inbox, LayoutGrid, Library, RefreshCw, Settings, SunMoon } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { CourseDot } from "@/components/ui/primitives";
import { backend } from "@/lib/backend";
import { relativeDue } from "@/lib/dates";
import { courseLabel } from "@/lib/items";
import { useCourses, useItems, useSetStatus, useSyncNow } from "@/lib/queries";
import { useUI } from "@/lib/store";

function useDebounced<T>(v: T, ms: number) {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = window.setTimeout(() => setD(v), ms);
    return () => window.clearTimeout(t);
  }, [v, ms]);
  return d;
}

const itemCls = "flex min-h-10 cursor-pointer items-center gap-2.5 rounded-lg px-3 text-body data-[selected=true]:bg-surface-2";

function Group({ heading, children }: { heading: string; children: ReactNode }) {
  return <Command.Group heading={heading} className="[&_[cmdk-group-heading]]:micro [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:text-faint">{children}</Command.Group>;
}

export function CommandPalette() {
  const { paletteOpen, setPaletteOpen, openItem, setMoveTarget, drawerItemId, theme, setTheme } = useUI();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 150);
  const { data: courses = [] } = useCourses();
  const { data: items = [] } = useItems();
  const sync = useSyncNow();
  const status = useSetStatus();
  const search = useQuery({
    queryKey: ["search", dq],
    queryFn: () => backend().searchItems(dq),
    enabled: paletteOpen && dq.trim().length >= 2,
  });
  const selected = drawerItemId ? items.find((w) => w.id === drawerItemId) : undefined;
  const close = () => { setPaletteOpen(false); setQ(""); };
  const go = (path: string) => { nav(path); close(); };

  return (
    <DialogP.Root open={paletteOpen} onOpenChange={(o) => (o ? setPaletteOpen(true) : close())}>
      <DialogP.Portal>
        <DialogP.Overlay className="fixed inset-0 z-40 bg-black/30" />
        <DialogP.Content className="fixed left-1/2 top-[12vh] z-50 w-[calc(100vw-32px)] max-w-xl -translate-x-1/2 overflow-hidden rounded-col border border-border bg-surface shadow-lift">
          <DialogP.Title className="sr-only">Search and commands</DialogP.Title>
          <DialogP.Description className="sr-only">Search items, jump to a course, or run an action.</DialogP.Description>
          <Command label="Command palette" shouldFilter={false} loop>
            <Command.Input value={q} onValueChange={setQ} autoFocus placeholder="Search items, courses, actions…" className="h-12 w-full border-b border-border bg-transparent px-4 text-emph outline-none placeholder:text-faint" />
            <Command.List className="max-h-[60vh] overflow-y-auto p-1.5">
              {dq.trim().length >= 2 && (
                <Group heading="Items">
                  {search.isFetching && !search.data && <div className="px-3 py-2 text-small text-faint">Searching…</div>}
                  {search.data?.length === 0 && <div className="px-3 py-2 text-small text-faint">No items match "{dq}".</div>}
                  {search.data?.map((w) => {
                    const c = courses.find((x) => x.id === w.course_id);
                    return (
                      <Command.Item key={w.id} value={`item-${w.id}`} onSelect={() => { openItem(w.id); close(); }} className={itemCls}>
                        <CourseDot index={c?.color_index ?? null} />
                        <span className="min-w-0 flex-1 truncate">{w.title}</span>
                        <span className="shrink-0 text-meta text-faint">{courseLabel(c)}{w.due_at ? ` · ${relativeDue(w.due_at)}` : ""}</span>
                      </Command.Item>
                    );
                  })}
                </Group>
              )}
              <Group heading="Actions">
                {[
                  { k: "sync", label: "Sync now", icon: <RefreshCw size={15} strokeWidth={1.5} />, run: () => { sync.mutate(); close(); } },
                  ...(selected ? [
                    { k: "move", label: `Move "${selected.title.slice(0, 40)}" to…`, icon: <FolderInput size={15} strokeWidth={1.5} />, run: () => { close(); setMoveTarget(selected.id); } },
                    { k: "submit", label: `Mark "${selected.title.slice(0, 40)}" submitted`, icon: <CheckCircle2 size={15} strokeWidth={1.5} />, run: () => { status.mutate({ id: selected.id, status: "submitted" }); close(); } },
                  ] : []),
                  { k: "theme", label: `Toggle theme (now ${theme})`, icon: <SunMoon size={15} strokeWidth={1.5} />, run: () => setTheme(theme === "dark" ? "light" : "dark") },
                ].filter((a) => !q || a.label.toLowerCase().includes(q.toLowerCase())).map((a) => (
                  <Command.Item key={a.k} value={`action-${a.k}`} onSelect={a.run} className={itemCls}>{a.icon}{a.label}</Command.Item>
                ))}
              </Group>
              <Group heading="Go to">
                {[
                  { p: "/today", l: "Today", i: <CalendarCheck size={15} strokeWidth={1.5} /> },
                  { p: "/board", l: "Board", i: <LayoutGrid size={15} strokeWidth={1.5} /> },
                  { p: "/review", l: "Needs Review", i: <Inbox size={15} strokeWidth={1.5} /> },
                  { p: "/courses", l: "Courses", i: <Library size={15} strokeWidth={1.5} /> },
                  { p: "/settings", l: "Settings", i: <Settings size={15} strokeWidth={1.5} /> },
                ].filter((x) => !q || x.l.toLowerCase().includes(q.toLowerCase())).map((x) => (
                  <Command.Item key={x.p} value={`nav-${x.p}`} onSelect={() => go(x.p)} className={itemCls}>{x.i}{x.l}</Command.Item>
                ))}
                {courses.filter((c) => !c.is_archived && (!q || `${c.name} ${c.short_name}`.toLowerCase().includes(q.toLowerCase()))).map((c) => (
                  <Command.Item key={c.id} value={`course-${c.id}`} onSelect={() => go(`/courses#${c.id}`)} className={itemCls}>
                    <CourseDot index={c.color_index} />{c.name}
                  </Command.Item>
                ))}
              </Group>
            </Command.List>
          </Command>
        </DialogP.Content>
      </DialogP.Portal>
    </DialogP.Root>
  );
}
