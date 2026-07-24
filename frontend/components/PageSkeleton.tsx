import { Section } from "./DetailKit";

/**
 * Loading placeholder for the detail pages. Rendered as a Suspense fallback
 * *inside* a page's existing <main>/back-link, so it only draws the inner
 * content skeleton (no wrapping <main> or back-link of its own).
 */

function SkeletonBlock({ className = "" }: { className?: string }) {
  return <div className={`w-full animate-pulse rounded-md bg-slate-warm-200 ${className}`} />;
}

export function PageSkeleton() {
  return (
    <div className="mt-6">
      <SkeletonBlock className="h-10 w-1/2" />
      <SkeletonBlock className="mt-4 h-6 w-3/4" />
      <div className="mt-12 space-y-10">
        <Section title="Loading…">
          <div className="space-y-4">
            <SkeletonBlock className="h-8" />
            <SkeletonBlock className="h-8" />
            <SkeletonBlock className="h-8 w-2/3" />
          </div>
        </Section>
        <Section title="Loading…">
          <div className="space-y-4">
            <SkeletonBlock className="h-8" />
            <SkeletonBlock className="h-8 w-5/6" />
          </div>
        </Section>
      </div>
    </div>
  );
}
