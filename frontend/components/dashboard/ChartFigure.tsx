/**
 * Frame shared by every dashboard chart: what it shows, the period and unit,
 * a one-sentence reading, the legend, its source and coverage, and the exact
 * numbers as a table. The table is the accessible version of the chart, so
 * chart bodies are aria-hidden and every figure stays checkable.
 */

import type { ReactNode } from "react";

export type LegendItem = {
  label: string;
  /** Background class of the swatch, e.g. "bg-series-house". */
  swatch?: string;
  /** Dashed outline instead of a fill, for "not collected" markers. */
  dashed?: boolean;
};

export type DataTable = {
  head: string[];
  /** First cell of each row is its row header. */
  rows: ReactNode[][];
};

export function ChartFigure({
  title,
  period,
  summary,
  legend,
  source,
  coverage,
  table,
  children,
}: {
  title: string;
  period?: ReactNode;
  summary: ReactNode;
  legend?: LegendItem[];
  source: ReactNode;
  coverage?: ReactNode;
  table: DataTable;
  children: ReactNode;
}) {
  return (
    <figure className="min-w-0">
      <figcaption>
        <h4 className="font-display text-sm font-bold text-ink">{title}</h4>
        {period && <p className="text-xs text-ink-muted">{period}</p>}
        <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{summary}</p>
      </figcaption>

      {legend && legend.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-soft">
          {legend.map((item) => (
            <li key={item.label} className="inline-flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className={`h-2.5 w-2.5 shrink-0 rounded-sm ${
                  item.dashed ? "border border-dashed border-ink-muted" : (item.swatch ?? "bg-slate-400")
                }`}
              />
              {item.label}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4">{children}</div>

      <dl className="mt-3 space-y-0.5 text-[11px] leading-snug text-ink-muted">
        <div>
          <dt className="inline font-semibold">Source: </dt>
          <dd className="inline">{source}</dd>
        </div>
        {coverage && (
          <div>
            <dt className="inline font-semibold">Coverage: </dt>
            <dd className="inline">{coverage}</dd>
          </div>
        )}
      </dl>

      <details className="mt-2 text-xs">
        <summary className="cursor-pointer select-none font-semibold text-govblue-600 transition-colors hover:text-ink">
          Show the data table
        </summary>
        <div className="mt-2 overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-left tabular-nums">
            <caption className="sr-only">{title}</caption>
            <thead className="bg-sunken text-ink-soft">
              <tr>
                {table.head.map((h, c) => (
                  <th key={h} scope="col" className={`px-3 py-1.5 font-semibold ${c > 0 ? "text-right" : ""}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line text-ink">
              {table.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) =>
                    c === 0 ? (
                      <th key={c} scope="row" className="whitespace-nowrap px-3 py-1.5 font-medium">
                        {cell}
                      </th>
                    ) : (
                      <td key={c} className="px-3 py-1.5 text-right">
                        {cell}
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
