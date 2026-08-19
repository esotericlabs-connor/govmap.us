"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { EmptyState, formatDate, Section } from "@/components/DetailKit";
import { publicApiBase, type DonationsResponse } from "@/lib/api";
import { formatMoney } from "@/lib/format";

const PAGE_SIZE = 50;

const SORTS: { value: string; label: string }[] = [
  { value: "amount", label: "Largest first" },
  { value: "amount_asc", label: "Smallest first" },
  { value: "date", label: "Newest first" },
  { value: "date_asc", label: "Oldest first" },
  { value: "name", label: "Name (A–Z)" },
];

function toTitle(s: string | null): string | null {
  if (!s) return null;
  // FEC stores names/employers in ALL CAPS; soften to Title Case for reading.
  return s
    .toLowerCase()
    .replace(/\b([a-z])/g, (m) => m.toUpperCase())
    .replace(/\b(Llc|Llp|Pac|Ii|Iii|Iv)\b/g, (m) => m.toUpperCase());
}

/**
 * Client-side itemized-donations ledger. Owns the search term, sort, and page
 * offset and refetches the list in place — the header, search box, sort control,
 * and footer stay mounted, and the previous rows stay visible (dimmed) while a
 * new page loads. This deliberately replaces the old server-driven approach
 * (`DonationControls` + a keyed `<Suspense>`), which remounted the whole subtree
 * on every keystroke, flashing a page skeleton and dropping input focus.
 *
 * Search/sort/paging update the URL via `history.replaceState` only — shareable,
 * but no Next navigation, so nothing on the page re-runs on the server.
 */
export function DonationsLedger({
  bioguide,
  initialCycle,
  cycles = [],
  initial,
  initSort,
  initQ,
  initOffset,
  urlSync = true,
}: {
  bioguide: string;
  initialCycle: number;
  cycles?: number[];
  initial: DonationsResponse;
  initSort: string;
  initQ: string;
  initOffset: number;
  urlSync?: boolean;
}) {
  const [data, setData] = useState<DonationsResponse>(initial);
  const [cycle, setCycle] = useState(initialCycle);
  const [term, setTerm] = useState(initQ); // live input value
  const [q, setQ] = useState(initQ); // applied (debounced) query
  const [sort, setSort] = useState(initSort);
  const [offset, setOffset] = useState(initOffset);
  const [pending, setPending] = useState(false);
  const [errored, setErrored] = useState(false);

  // We already have `initial` for the initial cycle/q/sort/offset, so skip the
  // first fetch the effect would otherwise fire on mount.
  const skipInitialFetch = useRef(true);
  // Monotonic request id so a slow earlier response can't overwrite a newer one.
  const reqId = useRef(0);

  // Debounce the search box → applied query (typing shouldn't fire a request per
  // keystroke). Cycle/sort/offset apply immediately via their handlers.
  useEffect(() => {
    if (term === q) return;
    const t = setTimeout(() => {
      setOffset(0);
      setQ(term.trim());
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [term]);

  // Refetch whenever the applied cycle/query/sort/offset changes.
  useEffect(() => {
    if (skipInitialFetch.current) {
      skipInitialFetch.current = false;
      return;
    }
    const id = ++reqId.current;
    setPending(true);
    setErrored(false);

    const params = new URLSearchParams({
      cycle: String(cycle),
      offset: String(offset),
      limit: String(PAGE_SIZE),
      sort,
    });
    if (q) params.set("q", q);

    fetch(`${publicApiBase}/api/members/${encodeURIComponent(bioguide)}/donations?${params.toString()}`)
      .then((r) => (r.ok ? (r.json() as Promise<DonationsResponse>) : Promise.reject(new Error(String(r.status)))))
      .then((next) => {
        if (id !== reqId.current) return; // a newer request superseded this one
        setData(next);
        setPending(false);
      })
      .catch(() => {
        if (id !== reqId.current) return;
        // Fail-soft: keep the last good page on screen, but tell the user.
        setPending(false);
        setErrored(true);
      });

    // Mirror state to the URL so it's shareable — replaceState, so Next never
    // re-runs the server component (that's what used to cause the blink). Skipped
    // in the blade (urlSync=false), where the blade owns the ?member= URL.
    if (urlSync) {
      const share = new URLSearchParams();
      share.set("cycle", String(cycle));
      if (offset > 0) share.set("offset", String(offset));
      if (sort && sort !== "amount") share.set("sort", sort);
      if (q) share.set("q", q);
      window.history.replaceState(null, "", `?${share.toString()}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cycle, q, sort, offset]);

  const items = data.items;
  const total = data.total;
  const shownFrom = items.length ? offset + 1 : 0;
  const shownTo = offset + items.length;
  const hasPrev = offset > 0;
  const hasNext = total !== null ? offset + PAGE_SIZE < total : items.length === PAGE_SIZE;
  // Always keep the selected cycle in the list (even if the FEC cycles fetch
  // failed or lags), newest first.
  const cycleOptions = Array.from(new Set([cycle, ...cycles])).sort((a, b) => b - a);

  return (
    <Section title="Contributions" count={total ?? undefined}>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <input
          type="search"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          placeholder="Search name, employer, or city…"
          aria-label="Search contributions"
          className="w-full rounded-full border border-slate-warm-200 bg-white px-4 py-2.5 text-sm text-slate-800 outline-none focus:border-govblue focus:ring-2 focus:ring-govblue/30 sm:max-w-sm"
        />
        <div className="flex flex-wrap items-center gap-3">
          {cycleOptions.length > 1 && (
            <label className="flex items-center gap-2 whitespace-nowrap text-sm text-slate-warm-500">
              Cycle
              <select
                value={cycle}
                onChange={(e) => {
                  setOffset(0);
                  setCycle(Number(e.target.value));
                }}
                aria-label="Election cycle"
                className="rounded-full border border-slate-warm-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 outline-none focus:border-govblue"
              >
                {cycleOptions.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="flex items-center gap-2 whitespace-nowrap text-sm text-slate-warm-500">
            Sort
            <select
              value={sort}
              onChange={(e) => {
                setOffset(0);
                setSort(e.target.value);
              }}
              className="rounded-full border border-slate-warm-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 outline-none focus:border-govblue"
            >
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {errored && (
        <p
          role="alert"
          className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-govred"
        >
          Couldn’t load contributions — showing the last results. Please try again.
        </p>
      )}

      {items.length === 0 ? (
        <EmptyState>
          {q
            ? `No contributions match “${q}”.`
            : `No itemized contributions found for this member in the ${cycle} cycle.`}
        </EmptyState>
      ) : (
        <div className={pending ? "pointer-events-none opacity-60 transition-opacity" : "transition-opacity"}>
          <ul className="-my-1 divide-y divide-slate-warm-100">
            {items.map((c) => {
              const name = toTitle(c.contributor_name) ?? "—";
              const place = [c.city ? toTitle(c.city) : null, c.state].filter(Boolean).join(", ");
              const work = [toTitle(c.occupation), toTitle(c.employer)].filter(Boolean).join(" · ");
              return (
                <li key={c.sub_id} className="flex items-start justify-between gap-4 py-3.5">
                  <div className="min-w-0">
                    <p className="font-semibold text-slate-800">{name}</p>
                    <p className="mt-0.5 text-sm text-slate-warm-500">
                      {place}
                      {place && work && " — "}
                      {work}
                    </p>
                  </div>
                  <div className="flex-shrink-0 text-right">
                    <p className="font-display text-lg font-bold text-govnavy">{formatMoney(c.amount)}</p>
                    {c.date && (
                      <p className="mt-0.5 text-sm text-slate-warm-400">{formatDate(c.date)}</p>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>

          <div className="mt-8 flex items-center justify-between border-t border-slate-warm-200 pt-6">
            <p className="text-sm text-slate-warm-500">
              {total !== null ? (
                <>
                  Showing <strong>{shownFrom.toLocaleString()}</strong>–
                  <strong>{shownTo.toLocaleString()}</strong> of{" "}
                  <strong>{total.toLocaleString()}</strong>
                </>
              ) : (
                <>
                  Showing {shownFrom.toLocaleString()}–{shownTo.toLocaleString()}
                </>
              )}
            </p>
            <div className="flex gap-2">
              <PagerButton onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} disabled={!hasPrev || pending}>
                ← Prev
              </PagerButton>
              <PagerButton onClick={() => setOffset(offset + PAGE_SIZE)} disabled={!hasNext || pending}>
                Next →
              </PagerButton>
            </div>
          </div>
        </div>
      )}

      <p className="mt-8 border-t border-slate-warm-200 pt-6 text-xs leading-relaxed text-slate-warm-400">
        Every disclosed contribution of <strong>$200 or more</strong> to this member&rsquo;s
        principal campaign committee. Small-dollar gifts under $200 aren&rsquo;t itemized by the FEC
        and so don&rsquo;t appear individually. Search and the alternate sorts cover the
        contributions loaded so far — browse the default largest-first view to load more. Records are
        pulled and cached on demand from the FEC. Source: Federal Election Commission.
      </p>
    </Section>
  );
}

function PagerButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void;
  disabled: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-full border border-slate-warm-200 px-4 py-2 text-sm font-semibold text-slate-warm-700 transition-colors enabled:hover:border-govnavy enabled:hover:text-govnavy disabled:cursor-not-allowed disabled:text-slate-warm-300"
    >
      {children}
    </button>
  );
}
