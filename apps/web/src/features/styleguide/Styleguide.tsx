import { useState } from "react";
import { Button, CourseDot, EmptyState, Input, Kbd, Pill, Segmented, Skeleton, StatusToggle, Textarea } from "@/components/ui/primitives";
import type { MyStatus, WorkItem } from "@/lib/types";
import { ItemCard } from "../board/ItemCard";

const now = Date.now();
const sample = (over: Partial<WorkItem>): WorkItem => ({
  id: crypto.randomUUID(), course_id: null, title: "Session 7 Lenskart Workbook", kind: "workbook", origin: "both",
  due_at: new Date(now + 2 * 86400_000).toISOString(), due_source: "nexus_field", instructions_md: null, links: [],
  nexus_status: "Pending", my_status: "pending", my_status_set_by: "default", my_note: null, classification: "auto",
  confidence: 1, classifier_reasons: [], is_hidden: false, upstream_due_at: null, due_changed_at: null,
  upstream_updated_at: null, first_seen_at: new Date().toISOString(), updated_at: new Date().toISOString(), ...over,
});
const CARDS = [
  sample({}),
  sample({ title: "Rapido Pricing Memo", kind: "assignment", due_at: new Date(now - 86400_000).toISOString() }),
  sample({ title: "Important: END TERM ASSIGNMENT – Crafting Marketing Strategy", kind: "announcement_task", origin: "notification_only", due_source: "parsed_from_text", due_at: new Date(now + 9 * 86400_000).toISOString(), due_changed_at: new Date().toISOString(), confidence: 0.72, classifier_reasons: [{ course_id: null, course: "CMS", score: 0.72, reasons: ["course name 'Crafting Marketing Strategies' (+0.60)", "alias 'marketing' (+0.12)"] }] }),
  sample({ title: "Framework Drill: Porter's Five Forces", my_status: "submitted", kind: "assignment" }),
  sample({ title: "Your BYOB leaderboard has been updated", kind: "info", due_at: null }),
];

function Panel({ theme }: { theme: "light" | "dark" }) {
  const [seg, setSeg] = useState<MyStatus>("pending");
  const [done, setDone] = useState<MyStatus>("pending");
  return (
    <div data-theme={theme} className="min-w-0 flex-1 space-y-6 rounded-col bg-bg p-5 text-text">
      <h2 className="font-display text-h2">{theme === "light" ? "Ivory & Forest" : "Obsidian & Champagne"}</h2>
      <div>
        <p className="micro mb-2 text-muted">Type</p>
        <p className="font-display text-h1">42</p>
        <p className="font-display text-h2">Heading two</p>
        <p className="text-h3 font-medium">Heading three</p>
        <p className="text-body">Body — the quick brown fox. <span className="text-muted">Muted</span> <span className="text-faint">Faint 12 Sep, 11:59 PM</span></p>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {["bg", "surface", "surface-2", "border", "primary", "accent", "danger", "warning", "success", "info"].map((t) => (
          <div key={t} className="flex flex-col items-center gap-1">
            <span className="h-10 w-10 rounded-lg border border-border" style={{ background: `var(--${t})` }} />
            <span className="text-meta text-faint">{t}</span>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">{Array.from({ length: 8 }, (_, i) => <CourseDot key={i} index={i} className="h-4 w-4" />)}</div>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary">Primary</Button><Button>Secondary</Button><Button variant="ghost">Ghost</Button><Button variant="danger">Danger</Button><Button disabled>Disabled</Button>
      </div>
      <div className="flex flex-wrap gap-2">
        <Pill>Neutral</Pill><Pill tone="danger">Overdue</Pill><Pill tone="warning">Deadline changed</Pill><Pill tone="success">Submitted</Pill><Pill tone="info">Updated</Pill><Pill tone="accent">Accent</Pill><Kbd>⌘K</Kbd>
      </div>
      <div className="flex items-center gap-3">
        <StatusToggle status={done} label="demo" onToggle={() => setDone(done === "submitted" ? "pending" : "submitted")} />
        <Segmented label="Status" value={seg} onChange={setSeg} options={[{ value: "pending", label: "Pending" }, { value: "in_progress", label: "In progress" }, { value: "submitted", label: "Submitted" }]} />
      </div>
      <div className="space-y-2"><Input placeholder="Input" /><Textarea placeholder="Textarea" /></div>
      <div className="well space-y-2 p-2">
        {CARDS.map((c) => <ItemCard key={c.id} item={c} courses={[]} course={{ id: "x", name: "Data Driven Decision Making", short_name: "DDDM", instructor: null, category: "core", mode: null, term: null, color_index: 0, is_archived: false }} />)}
        <ItemCard item={sample({ course_id: null, title: "Growth & GTM: 'What Is' Panel", kind: "info", classification: "unresolved" })} courses={[]} course={null} inReview />
      </div>
      <div className="space-y-2"><Skeleton className="h-6 w-1/2" /><Skeleton className="h-20" /></div>
      <EmptyState title="All sorted. Nice." body="Empty-state copy example." />
    </div>
  );
}

export default function Styleguide() {
  return (
    <div className="flex flex-col gap-4 p-4 md:p-6 xl:flex-row">
      <Panel theme="light" />
      <Panel theme="dark" />
    </div>
  );
}
