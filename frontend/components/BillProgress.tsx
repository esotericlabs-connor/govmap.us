import { formatDate, Section } from "@/components/DetailKit";
import type {
  BillProgress as Progress,
  Outcome,
  StepState,
} from "@/lib/bill-progress.mjs";

const STATE_WORD: Record<StepState, string> = {
  done: "Done",
  current: "Current step",
  upcoming: "Not yet",
  stopped: "Stopped",
  skipped: "Skipped",
  unreached: "Not reached",
};

const MARKER: Record<StepState, string> = {
  done: "bg-emerald-600 text-white",
  current: "bg-govblue text-white ring-4 ring-govblue/25",
  upcoming: "border-2 border-slate-warm-300 bg-white text-slate-warm-500",
  stopped: "bg-red-600 text-white",
  skipped: "border-2 border-dashed border-slate-warm-300 bg-white text-slate-warm-400",
  unreached: "border-2 border-slate-warm-200 bg-slate-warm-100 text-slate-warm-400",
};

const LABEL: Record<StepState, string> = {
  done: "text-govnavy",
  current: "text-govnavy",
  upcoming: "text-slate-warm-600",
  stopped: "text-red-700",
  skipped: "text-slate-warm-500",
  unreached: "text-slate-warm-400",
};

const STATE_TEXT: Record<StepState, string> = {
  done: "text-emerald-700",
  current: "text-govblue-600",
  upcoming: "text-slate-warm-500",
  stopped: "text-red-700",
  skipped: "text-slate-warm-500",
  unreached: "text-slate-warm-400",
};

const BAR: Record<Outcome, string> = {
  enacted: "bg-emerald-600",
  agreed: "bg-emerald-600",
  stopped: "bg-red-600",
  ended: "bg-slate-warm-400",
  active: "bg-govblue",
  unknown: "bg-slate-warm-300",
};

const PILL_GOOD = "bg-green-100/80 text-green-800 ring-green-600/30";
const PILL_BAD = "bg-red-100/80 text-red-800 ring-red-600/30";
const PILL_ACTIVE = "bg-govblue-100 text-govblue-600 ring-govblue/30";
const PILL_NEUTRAL = "bg-slate-warm-100 text-slate-warm-700 ring-slate-600/20";

/** A short outcome chip for the bill header; the full wording is in the card. */
export function OutcomePill({ progress }: { progress: Progress }) {
  const pill: Record<Outcome, [string, string] | null> = {
    enacted: ["Became law", PILL_GOOD],
    agreed: [progress.kind === "amendment" ? "Passed Congress" : "Agreed to", PILL_GOOD],
    stopped: ["Stopped", PILL_BAD],
    ended: ["Ended", PILL_NEUTRAL],
    active: ["In progress", PILL_ACTIVE],
    unknown: null,
  };
  const chosen = pill[progress.outcome];
  if (!chosen) return null;
  return (
    <p className={`inline-block rounded-full px-3 py-1 text-xs font-bold ring-1 ring-inset ${chosen[1]}`}>
      {chosen[0]}
    </p>
  );
}

function Mark({ state, index }: { state: StepState; index: number }) {
  const icon = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2.5,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    viewBox: "0 0 16 16",
    className: "h-4 w-4",
    "aria-hidden": true,
  } as const;
  switch (state) {
    case "done":
      return (
        <svg {...icon}>
          <path d="M3.5 8.5l3 3 6-7" />
        </svg>
      );
    case "stopped":
      return (
        <svg {...icon}>
          <path d="M4.5 4.5l7 7M11.5 4.5l-7 7" />
        </svg>
      );
    case "current":
      return <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-white" />;
    case "skipped":
      return <span aria-hidden="true" className="h-0.5 w-3 rounded-full bg-current" />;
    default:
      return (
        <span aria-hidden="true" className="text-xs font-bold">
          {index + 1}
        </span>
      );
  }
}

/**
 * Compact bill stepper derived from the official action log. The full log
 * remains on the bill page; the stepper does not predict outcomes.
 */
export function BillProgress({ progress }: { progress: Progress }) {
  const { steps, completed, outcome, headline, next, notes, noun } = progress;
  const percent = Math.round((completed / steps.length) * 100);

  return (
    <Section title="Where it stands">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          <p className="font-display text-2xl font-bold text-govnavy">{headline}</p>
          {next && (
            <p className="mt-1 text-sm text-slate-warm-600">
              <span className="font-semibold text-slate-warm-700">Next:</span> {next}
            </p>
          )}
        </div>
        <p className="shrink-0 text-sm font-semibold text-slate-warm-500">
          {completed} of {steps.length} steps
        </p>
      </div>
      <div aria-hidden="true" className="mt-4 h-1.5 overflow-hidden rounded-full bg-slate-warm-100">
        <div className={`h-full rounded-full ${BAR[outcome]}`} style={{ width: `${percent}%` }} />
      </div>
      <p className="mt-2 text-xs text-slate-warm-500">
        Milestones are not odds of becoming law; missing actions may leave steps incomplete.
      </p>

      <ol
        aria-label={`Steps for this ${noun}`}
        className="mt-6 grid gap-4 md:auto-cols-fr md:grid-flow-col md:gap-0"
      >
        {steps.map((step, i) => {
          const following = steps[i + 1];
          const travelled = following?.state === "done" || following?.state === "skipped";
          return (
            <li
              key={step.id}
              aria-current={step.state === "current" ? "step" : undefined}
              className="relative flex items-start gap-3 md:flex-col md:items-center md:gap-2 md:px-1 md:text-center"
            >
              {following && (
                <span
                  aria-hidden="true"
                  className={`absolute -bottom-3 left-[15px] top-9 w-0.5 rounded-full md:bottom-auto md:left-[calc(50%_+_1.25rem)] md:right-[calc(1.25rem_-_50%)] md:top-[15px] md:h-0.5 md:w-auto ${
                    travelled ? "bg-emerald-600" : "bg-slate-warm-200"
                  }`}
                />
              )}
              <span
                className={`relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${MARKER[step.state]}`}
              >
                <Mark state={step.state} index={i} />
              </span>
              <div className="min-w-0 pt-1 md:pt-0">
                <p className={`text-sm font-semibold leading-snug ${LABEL[step.state]}`}>{step.label}</p>
                <p className={`text-xs font-medium ${STATE_TEXT[step.state]}`}>
                  {STATE_WORD[step.state]}
                  {step.date ? ` · ${formatDate(step.date)}` : ""}
                </p>
              </div>
            </li>
          );
        })}
      </ol>

      {notes.length > 0 && (
        <ul className="mt-6 space-y-1.5 text-sm text-slate-warm-600">
          {notes.map((note) => (
            <li key={note} className="flex gap-2">
              <span aria-hidden="true" className="mt-2 h-1 w-1 shrink-0 rounded-full bg-slate-warm-400" />
              {note}
            </li>
          ))}
        </ul>
      )}

      <p className="mt-3 text-xs text-slate-warm-400">
        Source: Congress.gov · Full action history below
      </p>
    </Section>
  );
}
