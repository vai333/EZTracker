import { useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, CourseDot, EmptyState, Input, Pill, Skeleton, Tip } from "@/components/ui/primitives";
import { backend } from "@/lib/backend";
import { cn } from "@/lib/cn";
import { isDone } from "@/lib/dates";
import { useAliases, useCourses, useItems, usePatchCourse, qk } from "@/lib/queries";
import { useUI } from "@/lib/store";
import type { Course } from "@/lib/types";

function Aliases({ course }: { course: Course }) {
  const { data = [], isLoading } = useAliases(course.id);
  const qc = useQueryClient();
  const toast = useUI((s) => s.toast);
  const [v, setV] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: qk.aliases(course.id) });
  if (isLoading) return <Skeleton className="h-7 w-2/3" />;
  const order = { user: 0, learned: 1, seed: 2 } as const;
  return (
    <div>
      <div className="flex flex-wrap gap-1.5">
        {[...data].sort((a, b) => order[a.source] - order[b.source] || a.alias.localeCompare(b.alias)).map((a) => (
          <span key={a.id} className={cn("inline-flex h-7 items-center gap-1 rounded-full border pl-2.5 pr-1 text-meta",
            a.source === "learned" ? "border-accent text-accent-text" : "border-border text-muted")}>
            {a.alias}
            {a.source === "learned" && <span className="text-faint">· learned{a.weight < 0.5 ? " (weak)" : ""}</span>}
            <Tip content="Remove alias">
              <button
                aria-label={`Remove alias ${a.alias}`}
                className="grid h-6 w-6 place-items-center rounded-full hover:bg-surface-2"
                onClick={async () => {
                  try { await backend().deleteAlias(course.id, a.id); await refresh(); }
                  catch { toast({ title: "Couldn't remove alias", tone: "danger" }); }
                }}
              ><X size={12} /></button>
            </Tip>
          </span>
        ))}
        {data.length === 0 && <span className="text-small text-faint">No aliases yet.</span>}
      </div>
      <form className="mt-2 flex max-w-sm gap-2" onSubmit={async (e) => {
        e.preventDefault();
        if (v.trim().length < 2) return;
        try { await backend().addAlias(course.id, v.trim()); setV(""); await refresh(); }
        catch { toast({ title: "Couldn't add alias", tone: "danger" }); }
      }}>
        <Input value={v} onChange={(e) => setV(e.target.value)} placeholder="Add alias, e.g. a case company" aria-label={`Add alias for ${course.name}`} className="h-9" />
        <Button size="sm" aria-label="Add alias"><Plus size={15} /></Button>
      </form>
    </div>
  );
}

export default function CoursesView() {
  const { data: courses, isLoading } = useCourses();
  const { data: items = [] } = useItems();
  const patch = usePatchCourse();
  const [showArchived, setShowArchived] = useState(false);
  useEffect(() => {
    const id = location.hash.slice(1);
    if (id) document.getElementById(`course-${id}`)?.scrollIntoView({ block: "start" });
  }, [courses]);
  if (isLoading) return <div className="space-y-3 p-6"><Skeleton className="h-28" /><Skeleton className="h-28" /></div>;
  const list = (courses ?? []).filter((c) => showArchived || !c.is_archived);
  if (!list.length) return <EmptyState title="No courses yet" body="Courses appear after the first sync with Nexus." />;
  return (
    <div className="mx-auto max-w-4xl px-4 py-4 md:px-6">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-small text-muted">Aliases teach EZTracker which words point to which course. Learned ones come from your corrections.</p>
        <Button size="sm" variant="ghost" onClick={() => setShowArchived(!showArchived)} aria-pressed={showArchived}>
          {showArchived ? "Hide archived" : "Show archived"}
        </Button>
      </div>
      <ul className="space-y-3">
        {list.map((c) => {
          const mine = items.filter((w) => w.course_id === c.id && !w.is_hidden);
          const pending = mine.filter((w) => !isDone(w)).length;
          return (
            <li key={c.id} id={`course-${c.id}`} className={cn("card p-4", c.is_archived && "opacity-60")}>
              <div className="flex flex-wrap items-start gap-3">
                <CourseDot index={c.color_index} className="mt-2.5 h-2.5 w-2.5" />
                <div className="min-w-0 flex-1">
                  <h2 className="font-display text-h3">{c.name}</h2>
                  <p className="mt-0.5 flex flex-wrap items-center gap-2 text-small text-muted">
                    {c.category && c.category !== "other" && <Pill>{c.category === "soft_skills" ? "Soft Skills" : c.category === "core" ? "Core" : "Elective"}</Pill>}
                    {c.mode && <Pill>{c.mode}</Pill>}
                    {c.term && <span>{c.term}</span>}
                    <span>· {pending} pending · {mine.length} total</span>
                  </p>
                </div>
                <label className="flex items-center gap-2 text-small text-muted">
                  Short name
                  <Input defaultValue={c.short_name ?? ""} maxLength={40} className="h-9 w-32"
                    onBlur={(e) => e.target.value !== (c.short_name ?? "") && patch.mutate({ id: c.id, patch: { short_name: e.target.value || null } })} />
                </label>
                <Tip content={c.is_archived ? "Restore" : "Archive"}>
                  <Button variant="ghost" size="icon" aria-label={c.is_archived ? `Restore ${c.name}` : `Archive ${c.name}`}
                    onClick={() => patch.mutate({ id: c.id, patch: { is_archived: !c.is_archived } })}>
                    {c.is_archived ? <ArchiveRestore size={17} strokeWidth={1.5} /> : <Archive size={17} strokeWidth={1.5} />}
                  </Button>
                </Tip>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label={`Colour for ${c.name}`}>
                {Array.from({ length: 8 }, (_, i) => (
                  <button key={i} role="radio" aria-checked={c.color_index === i} aria-label={`Colour ${i + 1}`}
                    onClick={() => patch.mutate({ id: c.id, patch: { color_index: i } })}
                    className={cn("h-7 w-7 rounded-full border-2 transition-transform duration-press", c.color_index === i ? "scale-110 border-text" : "border-transparent")}
                    style={{ background: `var(--course-${i})` }} />
                ))}
              </div>
              <div className="mt-4">
                <p className="micro mb-2 text-muted">Aliases</p>
                <Aliases course={c} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
