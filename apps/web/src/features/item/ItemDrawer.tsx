import DOMPurify from "dompurify";
import { Command } from "cmdk";
import { Copy, ExternalLink, EyeOff, GitMerge, History, Link2, Pencil, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import Markdown from "react-markdown";
import { Button, CourseDot, Input, Label, Pill, Segmented, Skeleton, Textarea } from "@/components/ui/primitives";
import { Dialog, Drawer, DrawerClose, DrawerTitle, Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/overlays";
import { cn } from "@/lib/cn";
import { formatAbsolute, relativeDue, sinceLabel, TZ } from "@/lib/dates";
import { courseLabel } from "@/lib/items";
import { useCourses, useItemDetail, useItems, useMergeItems, useMoveItem, usePatchItem, useSetStatus } from "@/lib/queries";
import { useUI } from "@/lib/store";
import type { ItemEvent, MyStatus, WorkItem, WorkKind } from "@/lib/types";
import { KIND_LABEL, STATUS_LABEL } from "@/lib/types";
import { formatInTimeZone, fromZonedTime } from "date-fns-tz";

const EVENT_LABEL: Record<string, string> = {
  created: "First seen", moved: "Moved", status_changed: "Status changed", due_changed: "Deadline changed",
  due_changed_upstream: "Nexus changed the deadline", title_changed: "Title changed", merged: "Merged",
  hidden: "Hidden / shown", unhidden: "Unhidden (new deadline)", linked: "Linked a notification",
  instructions_changed: "Instructions updated", nexus_status_changed: "Nexus status changed", note_changed: "Note edited",
  edited: "Edited", undo: "Undone",
};

function toLocalInput(iso: string | null) {
  return iso ? formatInTimeZone(new Date(iso), TZ, "yyyy-MM-dd'T'HH:mm") : "";
}

function Instructions({ md }: { md: string | null }) {
  const [more, setMore] = useState(false);
  if (!md) return <p className="text-small text-faint">No instructions captured. Open it in Nexus for details.</p>;
  // Markdown is produced server-side from sanitized HTML; sanitize again in case any HTML survived.
  const safe = DOMPurify.sanitize(md, { ALLOWED_TAGS: [] , KEEP_CONTENT: true });
  const long = safe.length > 700;
  return (
    <div>
      <div className={cn("prose-ez relative", long && !more && "max-h-56 overflow-hidden")}>
        <Markdown components={{ a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer noopener">{children}</a> }}>{safe}</Markdown>
        {long && !more && <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-[var(--surface)]" />}
      </div>
      {long && <button className="mt-1 text-small font-medium text-accent-text" onClick={() => setMore(!more)}>{more ? "Show less" : "Show more"}</button>}
    </div>
  );
}

function HistoryList({ events }: { events: ItemEvent[] }) {
  if (!events.length) return <p className="text-small text-faint">No history yet.</p>;
  return (
    <ol className="relative space-y-3 border-l border-border pl-4">
      {events.map((e) => (
        <li key={e.id} className="relative">
          <span className={cn("absolute -left-[21px] top-1.5 h-2 w-2 rounded-full", e.actor === "user" ? "bg-accent" : "bg-border")} />
          <p className="text-small text-text">
            {EVENT_LABEL[e.event] ?? e.event}
            <span className="text-faint"> · {e.actor === "user" ? "you" : "Nexus sync"}</span>
          </p>
          <p className="text-meta text-faint">{formatAbsolute(e.created_at)}</p>
        </li>
      ))}
    </ol>
  );
}

function MergeDialog({ item, open, onOpenChange }: { item: WorkItem; open: boolean; onOpenChange: (v: boolean) => void }) {
  const { data: items = [] } = useItems();
  const merge = useMergeItems();
  const { openItem } = useUI();
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Merge with…" description={`Keeps "${item.title}" and folds the other item's sources, note and date into it.`}>
      <Command label="Pick an item to merge" className="rounded-lg border border-border">
        <Command.Input autoFocus placeholder="Search items…" className="h-10 w-full border-b border-border bg-transparent px-3 text-body outline-none" />
        <Command.List className="max-h-72 overflow-y-auto p-1">
          <Command.Empty className="p-4 text-center text-small text-muted">No matches.</Command.Empty>
          {items.filter((w) => w.id !== item.id && !w.is_hidden).map((w) => (
            <Command.Item key={w.id} value={`${w.title} ${w.id}`} onSelect={() => {
              merge.mutate({ keepId: item.id, mergeId: w.id }, { onSuccess: () => { onOpenChange(false); openItem(item.id); } });
            }} className="flex min-h-10 cursor-pointer items-center gap-2 rounded-md px-2 text-small data-[selected=true]:bg-surface-2">
              <span className="truncate">{w.title}</span>
              {w.due_at && <span className="ml-auto shrink-0 text-meta text-faint">{relativeDue(w.due_at)}</span>}
            </Command.Item>
          ))}
        </Command.List>
      </Command>
    </Dialog>
  );
}

function DrawerBody({ item }: { item: WorkItem }) {
  const { data: courses = [] } = useCourses();
  const detail = useItemDetail(item.id);
  const patch = usePatchItem();
  const quietPatch = usePatchItem({ quiet: true });
  const move = useMoveItem();
  const status = useSetStatus();
  const { openItem, toast } = useUI();
  const [editingTitle, setEditingTitle] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [note, setNote] = useState(item.my_note ?? "");
  const [noteState, setNoteState] = useState<"idle" | "saving" | "saved">("idle");
  const [merging, setMerging] = useState(false);
  const timer = useRef<number>();
  const course = courses.find((c) => c.id === item.course_id) ?? null;
  const nexusLink = item.links.find((l) => l.label === "Open in Nexus");
  const otherLinks = item.links.filter((l) => l !== nexusLink);

  useEffect(() => {
    setTitle(item.title);
  }, [item.title]);
  useEffect(() => {
    setNote(item.my_note ?? "");
    // only when switching items; don't clobber typing on refetch
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.id]);

  const onNote = (v: string) => {
    setNote(v);
    setNoteState("saving");
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      quietPatch.mutate({ id: item.id, patch: { my_note: v || null } }, { onSuccess: () => setNoteState("saved") });
    }, 600);
  };

  const summary = useMemo(() => [
    item.title,
    `${courseLabel(course)} · ${KIND_LABEL[item.kind]}`,
    item.due_at ? `Due: ${formatAbsolute(item.due_at)}` : "No due date",
    `Status: ${STATUS_LABEL[item.my_status]}`,
    nexusLink ? `Nexus: ${nexusLink.url}` : "",
  ].filter(Boolean).join("\n"), [item, course, nexusLink]);

  return (
    <>
      <header className="flex items-start gap-2 border-b border-border px-5 pb-4 pt-5">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2">
            <CourseDot index={course?.color_index ?? null} />
            <span className="micro text-muted">{courseLabel(course)} · {KIND_LABEL[item.kind]}</span>
          </div>
          {editingTitle ? (
            <form onSubmit={(e) => { e.preventDefault(); if (title.trim() && title !== item.title) patch.mutate({ id: item.id, patch: { title: title.trim() } }); setEditingTitle(false); }}>
              <Input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} onBlur={() => setEditingTitle(false)} aria-label="Title" className="font-display text-h3" />
            </form>
          ) : (
            <div className="group flex items-start gap-2">
              <DrawerTitle className="font-display text-h2 leading-tight">{item.title}</DrawerTitle>
              <button onClick={() => setEditingTitle(true)} aria-label="Edit title"
                className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-md text-faint opacity-60 hover:bg-surface-2 hover:text-text group-hover:opacity-100">
                <Pencil size={14} strokeWidth={1.5} />
              </button>
            </div>
          )}
        </div>
        <DrawerClose asChild>
          <Button variant="ghost" size="icon" aria-label="Close"><X size={18} strokeWidth={1.5} /></Button>
        </DrawerClose>
      </header>

      <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="d-course">Course</Label>
            <select id="d-course" value={item.course_id ?? ""} onChange={(e) => {
              const id = e.target.value || null;
              const c = courses.find((x) => x.id === id);
              move.mutate({ id: item.id, courseId: id, label: c ? courseLabel(c) : "Needs Review" });
            }} className="h-10 w-full rounded-lg border border-border bg-surface px-2 text-body">
              <option value="">Needs Review</option>
              {courses.filter((c) => !c.is_archived || c.id === item.course_id).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <Label htmlFor="d-kind">Kind</Label>
            <select id="d-kind" value={item.kind} onChange={(e) => patch.mutate({ id: item.id, patch: { kind: e.target.value as WorkKind } })}
              className="h-10 w-full rounded-lg border border-border bg-surface px-2 text-body">
              {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div className="sm:col-span-2">
            <Label htmlFor="d-due">
              Due · <span className="normal-case tracking-normal">{item.due_source === "user" ? "set by you" : item.due_source === "parsed_from_text" ? "parsed from text — please confirm" : item.due_source === "nexus_field" ? "from Nexus" : "none"}</span>
            </Label>
            <Input id="d-due" type="datetime-local" value={toLocalInput(item.due_at)}
              onChange={(e) => {
                const v = e.target.value;
                patch.mutate({ id: item.id, patch: { due_at: v ? fromZonedTime(v, TZ).toISOString() : null } });
              }} />
            {item.due_at && <p className="mt-1 text-meta text-muted">{formatAbsolute(item.due_at)} · {relativeDue(item.due_at)}</p>}
            {item.upstream_due_at && item.due_source === "user" && item.upstream_due_at !== item.due_at && (
              <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-info px-3 py-2 text-small">
                <span className="flex-1 text-text">Nexus says <strong>{formatAbsolute(item.upstream_due_at)}</strong> — use it?</span>
                <Button size="sm" onClick={() => patch.mutate({ id: item.id, patch: { due_at: item.upstream_due_at, due_use_upstream: true } })}>Use Nexus date</Button>
              </div>
            )}
          </div>
        </div>

        <div>
          <Label>Status</Label>
          <Segmented<MyStatus> label="My status" value={item.my_status}
            onChange={(v) => status.mutate({ id: item.id, status: v })}
            options={(["pending", "in_progress", "submitted", "not_applicable"] as MyStatus[]).map((s) => ({ value: s, label: STATUS_LABEL[s] }))} />
          {item.nexus_status && <p className="mt-1.5 text-meta text-faint">Nexus shows: {item.nexus_status}</p>}
        </div>

        <section>
          <h3 className="micro mb-2 text-muted">Instructions</h3>
          <Instructions md={item.instructions_md} />
        </section>

        <section>
          <h3 className="micro mb-2 text-muted">Links</h3>
          <div className="flex flex-wrap gap-2">
            {nexusLink && (
              <a href={nexusLink.url} target="_blank" rel="noreferrer noopener" className="inline-flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-body font-medium text-primary-fg hover:brightness-110">
                <ExternalLink size={15} strokeWidth={1.5} />Open in Nexus
              </a>
            )}
            {otherLinks.map((l) => (
              <a key={l.url} href={l.url} target="_blank" rel="noreferrer noopener" className="inline-flex h-10 items-center gap-2 rounded-lg border border-border px-3 text-small text-accent-text hover:bg-surface-2">
                <Link2 size={14} strokeWidth={1.5} />{l.label}
              </a>
            ))}
          </div>
        </section>

        <section>
          <h3 className="micro mb-2 text-muted">Sources</h3>
          {detail.isLoading ? <Skeleton className="h-12" /> : detail.data?.sources.length ? (
            <ul className="space-y-2">
              {detail.data.sources.map((s) => (
                <li key={s.id} className="rounded-lg border border-border px-3 py-2">
                  <div className="flex items-center gap-2">
                    {s.category_raw && <Pill>{s.category_raw}</Pill>}
                    <span className="text-meta text-faint">{s.published_at ? formatAbsolute(s.published_at) : ""}</span>
                  </div>
                  <p className="mt-1 text-small text-text">{s.snippet || s.title}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-small text-faint">{item.origin === "manual" ? "Added by you." : "From My Work only."}</p>
          )}
        </section>

        <section>
          <Label htmlFor="d-note">My note</Label>
          <Textarea id="d-note" value={note} onChange={(e) => onNote(e.target.value)} placeholder="Anything to remember — group mates, where the file is…" />
          <p className="mt-1 h-4 text-meta text-faint" aria-live="polite">{noteState === "saving" ? "Saving…" : noteState === "saved" ? "Saved" : ""}</p>
        </section>

        <section>
          <h3 className="micro mb-2 flex items-center gap-1.5 text-muted"><History size={13} strokeWidth={1.5} />History</h3>
          {detail.isLoading ? <Skeleton className="h-16" /> : <HistoryList events={detail.data?.events ?? []} />}
          <p className="mt-3 text-meta text-faint">First seen {sinceLabel(item.first_seen_at)}</p>
        </section>
      </div>

      <footer className="flex flex-wrap gap-2 border-t border-border px-5 py-3">
        <Button size="sm" variant="ghost" onClick={() => { patch.mutate({ id: item.id, patch: { is_hidden: !item.is_hidden } }); if (!item.is_hidden) openItem(null); }}>
          <EyeOff size={15} strokeWidth={1.5} />{item.is_hidden ? "Unhide" : "Hide"}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setMerging(true)}><GitMerge size={15} strokeWidth={1.5} />Merge with…</Button>
        <Menu>
          <MenuTrigger asChild>
            <Button size="sm" variant="ghost"><Copy size={15} strokeWidth={1.5} />Copy</Button>
          </MenuTrigger>
          <MenuContent align="start">
            <MenuItem onSelect={() => { void navigator.clipboard.writeText(summary); toast({ title: "Summary copied" }); }}>Copy summary</MenuItem>
            {nexusLink && <MenuItem onSelect={() => { void navigator.clipboard.writeText(nexusLink.url); toast({ title: "Link copied" }); }}>Copy Nexus link</MenuItem>}
          </MenuContent>
        </Menu>
      </footer>
      <MergeDialog item={item} open={merging} onOpenChange={setMerging} />
    </>
  );
}

export function ItemDrawer() {
  const { drawerItemId, openItem } = useUI();
  const { data: items } = useItems();
  const item = items?.find((w) => w.id === drawerItemId) ?? null;
  return (
    <Drawer open={!!item} onOpenChange={(o) => !o && openItem(null)}>
      {item && <DrawerBody key={item.id} item={item} />}
    </Drawer>
  );
}
