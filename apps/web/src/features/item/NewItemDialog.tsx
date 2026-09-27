import { fromZonedTime } from "date-fns-tz";
import { useState } from "react";
import { Dialog } from "@/components/ui/overlays";
import { Button, Input, Label } from "@/components/ui/primitives";
import { TZ } from "@/lib/dates";
import { useCourses, useCreateItem } from "@/lib/queries";
import { KIND_LABEL, type WorkKind } from "@/lib/types";

export function NewItemDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const { data: courses = [] } = useCourses();
  const create = useCreateItem();
  const [title, setTitle] = useState("");
  const [courseId, setCourseId] = useState("");
  const [kind, setKind] = useState<WorkKind>("assignment");
  const [due, setDue] = useState("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Add an item" description="For work that never showed up in Nexus.">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!title.trim()) return;
          create.mutate(
            { title: title.trim(), course_id: courseId || null, kind, due_at: due ? fromZonedTime(due, TZ).toISOString() : null },
            { onSuccess: () => { setTitle(""); setDue(""); onOpenChange(false); } },
          );
        }}
      >
        <div><Label htmlFor="n-title">Title</Label><Input id="n-title" autoFocus required value={title} onChange={(e) => setTitle(e.target.value)} /></div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="n-course">Course</Label>
            <select id="n-course" value={courseId} onChange={(e) => setCourseId(e.target.value)} className="h-10 w-full rounded-lg border border-border bg-surface px-2 text-body">
              <option value="">Needs Review</option>
              {courses.filter((c) => !c.is_archived).map((c) => <option key={c.id} value={c.id}>{c.short_name || c.name}</option>)}
            </select>
          </div>
          <div>
            <Label htmlFor="n-kind">Kind</Label>
            <select id="n-kind" value={kind} onChange={(e) => setKind(e.target.value as WorkKind)} className="h-10 w-full rounded-lg border border-border bg-surface px-2 text-body">
              {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
        </div>
        <div><Label htmlFor="n-due">Due</Label><Input id="n-due" type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} /></div>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" disabled={create.isPending}>Add</Button>
        </div>
      </form>
    </Dialog>
  );
}
