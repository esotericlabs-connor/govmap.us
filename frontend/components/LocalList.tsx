"use client";

import { useSearchParams } from "next/navigation";
import { Fragment, useCallback, useDeferredValue, useEffect, useState, type ReactNode } from "react";

import { compareListValues, localListQuery, matchesListQuery, reconcileListSearch } from "@/lib/list-controls.mjs";
import { withListHistory } from "@/lib/workspace-state";

export type LocalListItem = {
  id: string | number;
  text: string;
  name?: string | null;
  date?: string | null;
  group?: string | null;
  amount?: number | null;
  content: ReactNode;
};

export function LocalList({
  id,
  label,
  items,
  className = "space-y-3",
  as: Container = "div",
  tableHead,
  scope,
  groupLabel,
}: {
  id: string;
  label: string;
  items: LocalListItem[];
  className?: string;
  as?: "div" | "ul" | "ol";
  tableHead?: ReactNode;
  scope?: string;
  groupLabel?: string;
}) {
  const params = useSearchParams();
  const q = params.get(`${id}_q`) ?? "";
  const [search, setSearch] = useState<{ source: string; draft: string; submitted: string | null }>({ source: q, draft: q, submitted: null });
  const [historyError, setHistoryError] = useState(false);
  if (search.source !== q) setSearch(reconcileListSearch(search, q));
  const query = useDeferredValue(search.draft);
  const sort = params.get(`${id}_sort`) ?? "source";
  const group = params.get(`${id}_group`) ?? "";
  const groups = Array.from(new Set(items.map((item) => item.group).filter((value): value is string => !!value))).sort();
  const validSorts = ["source", "name", "name_desc", "newest", "oldest", "amount"];
  const invalid = !validSorts.includes(sort) || search.draft.length > 100;
  const shown = invalid ? [] : items.filter((item) => matchesListQuery(query, item.text) && (!group || item.group === group));
  if (!invalid && sort !== "source") {
    const field = sort === "newest" || sort === "oldest" ? "date" : sort === "amount" ? "amount" : "name";
    shown.sort((a, b) => compareListValues(a[field], b[field], sort === "newest" || sort === "amount" || sort === "name_desc"));
  }

  const replaceQuery = useCallback((next: URLSearchParams) => {
    try {
      const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      const href = `${window.location.pathname}${next.size ? `?${next}` : ""}${window.location.hash}`;
      window.history.replaceState(withListHistory(window.history.state, current, href), "", href);
      setHistoryError(false);
    } catch (error) {
      console.error("List controls could not save navigation state", error);
      setHistoryError(true);
    }
  }, []);

  const update = useCallback((key: string, value: string) => {
    if (key === "q") setSearch((current) => ({ ...current, submitted: value }));
    replaceQuery(localListQuery(window.location.search, id, key, value));
  }, [id, replaceQuery]);

  useEffect(() => {
    if (search.draft === q) return;
    const timer = setTimeout(() => update("q", search.draft), 250);
    return () => clearTimeout(timer);
  }, [search.draft, q, update]);

  return (
    <div className="min-w-0 space-y-3" aria-busy={search.draft !== query}>
      <div role="search" aria-label={`Search ${label}`} className="flex flex-wrap items-center gap-2">
        <input aria-label={`Search ${label}`} type="search" maxLength={100} value={search.draft} onChange={(event) => {
          const value = event.target.value;
          setSearch((current) => ({ ...current, draft: value }));
        }} onBlur={() => {
          if (search.draft !== q) update("q", search.draft);
        }} placeholder={`Search ${label.toLowerCase()}`} className="h-10 min-w-32 flex-1 rounded-lg border border-line bg-canvas px-3 text-base text-ink focus:border-govblue-600 focus:outline-none focus:ring-2 focus:ring-govblue-600/20 sm:text-sm" />
        <select aria-label={`Sort ${label}`} value={sort} onChange={(event) => update("sort", event.target.value)} className="h-10 max-w-40 rounded-lg border border-line bg-canvas px-2 text-base text-ink sm:text-sm">
          <option value="source">Source order</option>
          {items.some((item) => item.name !== undefined) && <><option value="name">Name A-Z</option><option value="name_desc">Name Z-A</option></>}
          {items.some((item) => item.date !== undefined) && <><option value="newest">Newest first</option><option value="oldest">Oldest first</option></>}
          {items.some((item) => item.amount !== undefined) && <option value="amount">Largest first</option>}
        </select>
        {groupLabel && groups.length > 0 && (
          <select aria-label={`Filter ${label} by ${groupLabel}`} value={group} onChange={(event) => update("group", event.target.value)} className="h-10 max-w-48 rounded-lg border border-line bg-canvas px-2 text-base text-ink sm:text-sm">
            <option value="">All {groupLabel}</option>
            {groups.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        )}
        {(search.draft || sort !== "source" || group) && (
          <button type="button" className="text-sm font-semibold text-govblue-600" onClick={() => {
            const next = new URLSearchParams(window.location.search);
            for (const key of ["q", "sort", "group"]) next.delete(`${id}_${key}`);
            setSearch({ source: q, draft: "", submitted: "" });
            replaceQuery(next);
          }}>Clear</button>
        )}
      </div>
      {historyError && <p role="alert" className="text-sm text-govred">List controls could not be saved in navigation history. Please refresh and try again.</p>}
      <p role="status" className="text-xs text-ink-muted">
        {shown.length.toLocaleString()} of {items.length.toLocaleString()} {label.toLowerCase()}{scope ? ` · ${scope}` : ""}
      </p>
      {invalid ? (
        <p role="alert" className="text-sm text-govred">Invalid list criteria. Clear the filters or choose a supported sort and a search of at most 100 characters.</p>
      ) : shown.length === 0 ? (
        <p className="rounded-lg border border-line p-4 text-sm text-ink-soft">No matching {label.toLowerCase()}. Try a different search or clear the filters.</p>
      ) : tableHead ? (
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">{label}</caption>
            <thead className="border-b border-line bg-sunken text-ink-soft">{tableHead}</thead>
            <tbody className={className}>{shown.map((item) => <Fragment key={item.id}>{item.content}</Fragment>)}</tbody>
          </table>
        </div>
      ) : (
        <Container className={className}>{shown.map((item) => <Fragment key={item.id}>{item.content}</Fragment>)}</Container>
      )}
    </div>
  );
}
