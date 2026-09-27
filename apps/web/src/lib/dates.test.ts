import { agendaGroup, byDue, urgency } from "./dates";
import { boardColumns, summarize } from "./items";
import type { Course, WorkItem } from "./types";

const NOW = new Date("2026-09-27T06:00:00Z");
const h = (hours: number) => new Date(NOW.getTime() + hours * 3600_000).toISOString();
const item = (o: Partial<WorkItem>): WorkItem => ({
  id: Math.random().toString(36), course_id: "c1", title: "x", kind: "assignment", origin: "assignments_tab",
  due_at: null, due_source: null, instructions_md: null, links: [], nexus_status: null, my_status: "pending",
  my_status_set_by: "default", my_note: null, classification: "auto", confidence: 1, classifier_reasons: [],
  is_hidden: false, upstream_due_at: null, due_changed_at: null, upstream_updated_at: null,
  first_seen_at: NOW.toISOString(), updated_at: NOW.toISOString(), ...o,
});

describe("urgency", () => {
  it("classifies overdue / soon / later / done", () => {
    expect(urgency(item({ due_at: h(-1) }), NOW)).toBe("overdue");
    expect(urgency(item({ due_at: h(71) }), NOW)).toBe("soon");
    expect(urgency(item({ due_at: h(100) }), NOW)).toBe("later");
    expect(urgency(item({ due_at: h(-1), my_status: "submitted" }), NOW)).toBe("done");
    expect(urgency(item({}), NOW)).toBe("none");
  });
});

describe("agendaGroup", () => {
  it("buckets by calendar day", () => {
    expect(agendaGroup(item({ due_at: h(-5) }), NOW)).toBe("Overdue");
    expect(agendaGroup(item({ due_at: h(2) }), NOW)).toBe("Today");
    expect(agendaGroup(item({ due_at: h(26) }), NOW)).toBe("Tomorrow");
    expect(agendaGroup(item({ due_at: h(24 * 4) }), NOW)).toBe("This week");
    expect(agendaGroup(item({ due_at: h(24 * 12) }), NOW)).toBe("Later");
    expect(agendaGroup(item({}), NOW)).toBe("No due date");
  });
});

describe("summaries", () => {
  it("counts the Today strip and ignores hidden items", () => {
    const s = summarize([
      item({ due_at: h(-2) }), item({ due_at: h(10) }), item({ course_id: null, kind: "info" }),
      item({ my_status: "submitted", due_at: h(-50) }), item({ due_at: h(-3), is_hidden: true }),
    ], NOW);
    expect(s).toMatchObject({ overdue: 1, soon: 1, review: 1, submitted: 1, total: 3 });
  });

  it("orders pending before done, then by due date", () => {
    const a = item({ title: "a", due_at: h(50) }), b = item({ title: "b", due_at: h(5) }), c = item({ title: "c", my_status: "submitted", due_at: h(1) });
    expect([a, c, b].sort(byDue).map((w) => w.title)).toEqual(["b", "a", "c"]);
  });

  it("orders board columns by nearest pending due, archived excluded", () => {
    const course = (id: string, name: string, archived = false): Course =>
      ({ id, name, short_name: null, instructor: null, category: "core", mode: null, term: null, color_index: 0, is_archived: archived });
    const cols = boardColumns([course("a", "Alpha"), course("b", "Beta"), course("z", "Zed", true)],
      [item({ course_id: "b", due_at: h(3) }), item({ course_id: "a", due_at: h(30) })], "due");
    expect(cols.map((c) => c.id)).toEqual(["b", "a"]);
  });
});
