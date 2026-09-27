import { Command } from "cmdk";
import { Check, Inbox } from "lucide-react";
import * as DialogP from "@radix-ui/react-dialog";
import { CourseDot } from "@/components/ui/primitives";
import { courseLabel } from "@/lib/items";
import { useCourses, useItems, useMoveItem } from "@/lib/queries";
import { useUI } from "@/lib/store";

/** Keyboard/touch alternative to drag and drop: a command-palette style course picker. */
export function MoveToDialog() {
  const { moveTargetId, setMoveTarget } = useUI();
  const { data: items } = useItems();
  const { data: courses = [] } = useCourses();
  const move = useMoveItem();
  const item = items?.find((w) => w.id === moveTargetId);
  const pick = (courseId: string | null, label: string) => {
    if (item && item.course_id !== courseId) move.mutate({ id: item.id, courseId, label });
    setMoveTarget(null);
  };
  return (
    <DialogP.Root open={!!item} onOpenChange={(o) => !o && setMoveTarget(null)}>
      <DialogP.Portal>
        <DialogP.Overlay className="fixed inset-0 z-40 bg-black/30" />
        <DialogP.Content className="fixed left-1/2 top-[14vh] z-50 w-[calc(100vw-32px)] max-w-md -translate-x-1/2 overflow-hidden rounded-col border border-border bg-surface shadow-lift">
          <DialogP.Title className="sr-only">Move to…</DialogP.Title>
          <DialogP.Description className="sr-only">Choose a course for {item?.title}</DialogP.Description>
          <Command label="Move to course" loop>
            <div className="border-b border-border px-4 pb-2 pt-3">
              <p className="micro text-faint">Move to…</p>
              <p className="truncate text-small text-muted">{item?.title}</p>
            </div>
            <Command.Input autoFocus placeholder="Type a course…" className="h-11 w-full border-b border-border bg-transparent px-4 text-body outline-none placeholder:text-faint" />
            <Command.List className="max-h-[50vh] overflow-y-auto p-1">
              <Command.Empty className="px-4 py-6 text-center text-small text-muted">No course matches.</Command.Empty>
              <Command.Item value="needs review" onSelect={() => pick(null, "Needs Review")}
                className="flex h-10 cursor-pointer items-center gap-2.5 rounded-lg px-3 text-body data-[selected=true]:bg-surface-2">
                <Inbox size={15} strokeWidth={1.5} className="text-accent-text" /> Needs Review
                {item?.course_id === null && <Check size={15} className="ml-auto text-success" />}
              </Command.Item>
              {courses.filter((c) => !c.is_archived).map((c) => (
                <Command.Item key={c.id} value={`${c.name} ${c.short_name ?? ""}`} onSelect={() => pick(c.id, courseLabel(c))}
                  className="flex h-10 cursor-pointer items-center gap-2.5 rounded-lg px-3 text-body data-[selected=true]:bg-surface-2">
                  <CourseDot index={c.color_index} />
                  <span className="truncate">{c.name}</span>
                  {item?.course_id === c.id && <Check size={15} className="ml-auto text-success" />}
                </Command.Item>
              ))}
            </Command.List>
          </Command>
        </DialogP.Content>
      </DialogP.Portal>
    </DialogP.Root>
  );
}
