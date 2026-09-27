import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as TooltipP from "@radix-ui/react-tooltip";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import type { Course, WorkItem } from "@/lib/types";
import { ItemCard } from "./ItemCard";

const wrap = (ui: ReactNode) =>
  render(<QueryClientProvider client={new QueryClient()}><TooltipP.Provider>{ui}</TooltipP.Provider></QueryClientProvider>);

const course: Course = { id: "c1", name: "Data Driven Decision Making", short_name: "DDDM", instructor: null, category: "core", mode: null, term: null, color_index: 2, is_archived: false };
const base: WorkItem = {
  id: "w1", course_id: null, title: "Session 7 Lenskart Workbook", kind: "workbook", origin: "notification_only",
  due_at: null, due_source: null, instructions_md: null, links: [], nexus_status: null, my_status: "pending",
  my_status_set_by: "default", my_note: null, classification: "unresolved", confidence: 0.45,
  classifier_reasons: [{ course_id: "c1", course: "DDDM", score: 0.45, reasons: ["alias 'lenskart' (+0.25)"] }],
  is_hidden: false, upstream_due_at: null, due_changed_at: null, upstream_updated_at: null,
  first_seen_at: "2026-09-27T00:00:00Z", updated_at: "2026-09-27T00:00:00Z",
};

describe("ItemCard", () => {
  it("shows one-tap suggestion chips in Needs Review", () => {
    wrap(<ItemCard item={base} courses={[course]} course={null} inReview />);
    expect(screen.getByText("Suggested:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /DDDM/ })).toBeInTheDocument();
  });

  it("exposes an accessible submit toggle and Move to… control", () => {
    wrap(<ItemCard item={{ ...base, course_id: "c1", classification: "auto" }} courses={[course]} course={course} />);
    expect(screen.getByRole("button", { name: 'Mark "Session 7 Lenskart Workbook" as submitted' })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: 'Move "Session 7 Lenskart Workbook" to…' })).toBeInTheDocument();
    expect(screen.getByText("No due date")).toBeInTheDocument();
  });

  it("marks overdue with text, not colour alone", () => {
    wrap(<ItemCard item={{ ...base, course_id: "c1", due_at: new Date(Date.now() - 3600_000).toISOString() }} courses={[course]} course={course} />);
    expect(screen.getByText("Overdue:")).toBeInTheDocument();
  });

  it("renders info items as a compact muted line", () => {
    wrap(<ItemCard item={{ ...base, kind: "info", course_id: "c1" }} courses={[course]} course={course} />);
    expect(screen.getByText("Info")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Mark/ })).not.toBeInTheDocument();
  });
});
