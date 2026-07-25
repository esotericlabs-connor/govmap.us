"use client";

import { BugReport } from "@/components/BugReport";

/**
 * Route-segment error boundary. Renders a friendly screen for an unexpected
 * client/render error and lets the visitor file a report pre-filled with the
 * error (its `digest` correlates with the server-side entry in app.log).
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="flex min-h-[70vh] flex-col items-center justify-center bg-slate-warm-50 px-6 text-center">
      <p className="font-mono text-sm font-semibold uppercase tracking-wider text-govred">Error</p>
      <h1 className="mt-3 font-display text-3xl font-bold tracking-tight text-govnavy sm:text-4xl">
        Something went wrong
      </h1>
      <p className="mt-3 max-w-md text-slate-warm-600">
        An unexpected error occurred on this page. You can try again, or tell us what happened so we
        can fix it.
      </p>
      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <button
          type="button"
          onClick={reset}
          className="rounded-full bg-govnavy px-6 py-2.5 text-sm font-semibold text-white transition-transform hover:-translate-y-px"
        >
          Try again
        </button>
        <BugReport
          triggerClassName="rounded-full border border-slate-warm-300 bg-white px-6 py-2.5 text-sm font-semibold text-govnavy transition-colors hover:border-govblue hover:text-govblue"
          triggerLabel="Report this problem"
          prefill={{
            category: "Site / UI",
            subcategory: "Something else",
            message: `[auto] ${error.message}${error.digest ? ` (digest ${error.digest})` : ""}`,
          }}
        />
      </div>
    </main>
  );
}
