import { LayoutGroup, motion, MotionConfig } from "framer-motion";
import { useSearchParams } from "react-router-dom";
import { EmptyState, Skeleton } from "@/components/ui/primitives";
import { byDue } from "@/lib/dates";
import { isNeedsReview } from "@/lib/items";
import { useCourses, useItems } from "@/lib/queries";
import { ItemCard } from "./ItemCard";

export default function NeedsReviewView() {
  const { data: items, isLoading } = useItems();
  const { data: courses = [] } = useCourses();
  const [params] = useSearchParams();
  const list = (items ?? []).filter(isNeedsReview).sort(byDue);
  const first = params.has("first");
  if (isLoading) return <div className="space-y-2 p-6"><Skeleton className="h-24" /><Skeleton className="h-24" /></div>;
  return (
    <div className="mx-auto max-w-3xl px-4 py-4 md:px-6">
      <p className="text-body text-muted">
        {list.length > 0
          ? first
            ? `Help EZTracker learn — sort these ${list.length}. Each choice teaches it for next time.`
            : "EZTracker wasn't confident about these. Tap a suggestion, press M, or drag them on the Board."
          : ""}
      </p>
      {list.length === 0 ? (
        <EmptyState title="All sorted. Nice." body="Anything EZTracker can't place with confidence will show up here after the next sync." />
      ) : (
        <MotionConfig reducedMotion="user">
          <LayoutGroup>
            <ul className="mt-4 flex flex-col gap-2">
              {list.map((w) => (
                <motion.li key={w.id} layout exit={{ opacity: 0 }} transition={{ duration: 0.24 }}>
                  <ItemCard item={w} course={null} courses={courses} inReview />
                </motion.li>
              ))}
            </ul>
          </LayoutGroup>
        </MotionConfig>
      )}
    </div>
  );
}
