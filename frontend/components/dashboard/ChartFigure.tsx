/**
 * Frame shared by every dashboard chart: what it shows, the period and unit,
 * a one-sentence reading, the legend, its source and coverage, and the exact
 * numbers as a table. Decorative chart marks are aria-hidden; interactive
 * labels stay accessible, and every figure stays checkable.
 */

import { isValidElement, type ReactNode } from "react";

import { LocalList } from "@/components/LocalList";

function cellText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number" || typeof node === "bigint") return String(node);
  if (Array.isArray(node)) return node.map(cellText).join(" ");
  if (isValidElement<{ children?: ReactNode }>(node)) return cellText(node.props.children);
  return "";
}

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
        <div className="mt-2">
          <LocalList
            id={`chart-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}
            label="Table rows"
            scope="Table only; the chart and its source coverage are unchanged"
            className="divide-y divide-line text-ink tabular-nums"
            tableHead={
              <tr>
                {table.head.map((h, c) => (
                  <th key={h} scope="col" className={`px-3 py-1.5 font-semibold ${c > 0 ? "text-right" : ""}`}>
                    {h}
                  </th>
                ))}
              </tr>
            }
            items={table.rows.map((row, r) => ({
              id: r,
              name: cellText(row[0]),
              text: row.map(cellText).join(" "),
              content: (
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
              ),
            }))}
          />
        </div>
      </details>
    </figure>
  );
}
