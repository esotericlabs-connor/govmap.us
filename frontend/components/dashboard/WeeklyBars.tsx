/**
 * Grouped weekly bar chart drawn with CSS boxes rather than SVG, so axis text
 * stays readable at phone widths. A null value means the week isn't covered
 * by the stored records and draws a dashed stub; a zero draws no bar. Pair it
 * with ChartFigure, whose table is the accessible equivalent.
 */

import { formatWeek, labeledIndexes, niceScale, percentOf } from "@/lib/chart-scales.mjs";

export type BarSeries = {
  label: string;
  values: (number | null)[];
  /** Background class of the bars, e.g. "bg-series-house". */
  barClass: string;
};

function describe(week: string, partial: boolean, series: BarSeries[], i: number): string {
  const parts = series.map((s) => {
    const v = s.values[i] ?? null;
    return `${s.label} ${v === null ? "not collected" : v.toLocaleString("en-US")}`;
  });
  return `Week of ${formatWeek(week)}${partial ? " (so far)" : ""}: ${parts.join(" · ")}`;
}

export function WeeklyBars({
  weeks,
  series,
  lastIsPartial = true,
}: {
  /** ISO date (Monday) per week, oldest first. */
  weeks: string[];
  series: BarSeries[];
  /** Draw the last week lighter as a week still in progress. */
  lastIsPartial?: boolean;
}) {
  const max = Math.max(0, ...series.flatMap((s) => s.values.map((v) => v ?? 0)));
  const scale = niceScale(max);
  const labels = labeledIndexes(weeks.length);

  return (
    <div aria-hidden="true" className="select-none">
      <div className="flex gap-2">
        <div className="relative h-44 w-8 shrink-0 text-[10px] tabular-nums text-ink-muted">
          {scale.ticks.map((t) => (
            <span
              key={t}
              className="absolute right-0 translate-y-1/2 leading-none"
              style={{ bottom: `${percentOf(t, scale.max)}%` }}
            >
              {t.toLocaleString("en-US")}
            </span>
          ))}
        </div>
        <div className="relative h-44 min-w-0 flex-1">
          {scale.ticks.map((t) => (
            <div
              key={t}
              className={`absolute inset-x-0 border-t ${t === 0 ? "border-ink-muted/60" : "border-line"}`}
              style={{ bottom: `${percentOf(t, scale.max)}%` }}
            />
          ))}
          <div className="absolute inset-0 flex items-end gap-1 sm:gap-1.5">
            {weeks.map((week, i) => {
              const partial = lastIsPartial && i === weeks.length - 1;
              return (
                <div
                  key={week}
                  title={describe(week, partial, series, i)}
                  className={`flex h-full min-w-0 flex-1 items-end justify-center gap-px rounded-sm transition-colors hover:bg-sunken/70 ${
                    partial ? "opacity-60" : ""
                  }`}
                >
                  {series.map((s) => {
                    const v = s.values[i] ?? null;
                    return (
                      <div key={s.label} className="flex h-full w-full max-w-[0.75rem] items-end">
                        {v === null ? (
                          <div className="h-1.5 w-full rounded-sm border border-dashed border-ink-muted/70" />
                        ) : v > 0 ? (
                          <div
                            className={`w-full rounded-t-sm ${s.barClass}`}
                            style={{ height: `${percentOf(v, scale.max)}%`, minHeight: 2 }}
                          />
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="ml-10 mt-1.5 flex gap-1 text-[10px] text-ink-muted sm:gap-1.5">
        {weeks.map((week, i) => (
          <span key={week} className="flex min-w-0 flex-1 justify-center whitespace-nowrap">
            {labels.has(i) ? formatWeek(week) : ""}
          </span>
        ))}
      </div>
    </div>
  );
}
