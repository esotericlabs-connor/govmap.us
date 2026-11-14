/**
 * Base surfaces of the dashboard: a titled panel and a headline metric. Server
 * components with no hooks, themed through the semantic color tokens.
 */

import Link from "next/link";
import type { ReactNode } from "react";

export function Panel({
  title,
  eyebrow,
  action,
  children,
  className = "",
  id,
  level = 3,
}: {
  title?: ReactNode;
  eyebrow?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
  /** Heading level of the title, so a panel can open a page section (2) or sit inside one (3). */
  level?: 2 | 3;
}) {
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <section id={id} className={`rounded-2xl border border-line bg-panel shadow-card ${className}`}>
      {(title || eyebrow || action) && (
        <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 border-b border-line px-5 py-3.5">
          <div className="min-w-0">
            {eyebrow && (
              <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{eyebrow}</p>
            )}
            {title && <Heading className="font-display text-base font-bold text-ink">{title}</Heading>}
          </div>
          {action && <div className="shrink-0 text-sm">{action}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

/** One headline figure. With `href` the whole card links to the records behind it. */
export function Metric({
  label,
  value,
  detail,
  href,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  href?: string;
}) {
  const body = (
    <>
      <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{label}</p>
      <p className="mt-1 font-display text-3xl font-bold tabular-nums tracking-tight text-ink">{value}</p>
      {detail && <p className="mt-1 text-xs leading-snug text-ink-soft">{detail}</p>}
    </>
  );
  const base = "block h-full rounded-xl border border-line bg-panel p-4 shadow-sm";
  if (!href) return <div className={base}>{body}</div>;
  return (
    <Link
      href={href}
      className={`${base} transition duration-200 hover:-translate-y-0.5 hover:border-govblue-400 hover:shadow-card-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-govblue-600 motion-reduce:transition-none motion-reduce:hover:translate-y-0`}
    >
      {body}
    </Link>
  );
}

/** A small arrow link for panel headers ("Open the map →"). */
export function PanelLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1 font-semibold text-govblue-600 transition-colors hover:text-ink"
    >
      {children}
      <span aria-hidden="true">→</span>
    </Link>
  );
}
