"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { publicApiBase, type SearchResults } from "@/lib/api";

/**
 * The platform's "search everything" box. Debounced, abortable typeahead over
 * /api/search; renders grouped results (members, bills, votes, committees) that
 * each navigate to a real detail page. Query is URL-encoded; results are React
 * text nodes (auto-escaped) — no innerHTML.
 */

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
      <path d="M20 20l-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function isEmpty(r: SearchResults | null): boolean {
  return (
    !r ||
    (r.members.length === 0 &&
      r.bills.length === 0 &&
      r.votes.length === 0 &&
      r.committees.length === 0)
  );
}

export function UniversalSearch({
  className = "",
  onNavigate,
}: {
  className?: string;
  onNavigate?: () => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Debounced + abortable fetch.
  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setResults(null);
      setLoading(false);
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetch(
          `${publicApiBase}/api/search?q=${encodeURIComponent(term)}`,
          { signal: ctrl.signal },
        );
        if (res.ok) setResults((await res.json()) as SearchResults);
      } catch {
        // aborted or network hiccup — leave prior results, stay quiet
      } finally {
        setLoading(false);
      }
    }, 220);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [query]);

  // Close on outside click.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const close = () => {
    setOpen(false);
    onNavigate?.();
  };

  const showPanel = open && query.trim().length >= 2;

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <div className="flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-4 py-2 text-white/90 focus-within:border-white/40 focus-within:bg-white/15">
        <span className="text-white/50">
          <SearchIcon />
        </span>
        <input
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setOpen(false);
              (e.target as HTMLInputElement).blur();
            }
          }}
          placeholder="Search members, bills, votes, committees…"
          aria-label="Search the platform"
          className="w-full bg-transparent text-sm text-white placeholder:text-white/45 focus:outline-none"
        />
      </div>

      {showPanel && (
        <div className="absolute left-0 right-0 top-full z-50 mt-2 max-h-[70vh] overflow-y-auto rounded-xl border border-slate-200 bg-white text-slate-800 shadow-card">
          {isEmpty(results) ? (
            <p className="px-4 py-6 text-center text-sm text-slate-400">
              {loading ? "Searching…" : `No matches for “${query.trim()}”.`}
            </p>
          ) : (
            <div className="py-2">
              {results!.members.length > 0 && (
                <Group label="Members">
                  {results!.members.map((m) => (
                    <Row key={m.bioguide_id} href={`/members/${m.bioguide_id}`} onClick={close}>
                      <span className="font-medium">{m.official_full_name}</span>
                      <span className="text-xs text-slate-400">
                        {m.party?.slice(0, 1)} · {m.state}
                      </span>
                    </Row>
                  ))}
                </Group>
              )}
              {results!.bills.length > 0 && (
                <Group label="Bills">
                  {results!.bills.map((b) => (
                    <Row key={b.bill_id} href={`/bills/${b.bill_id}`} onClick={close}>
                      <span className="truncate">{b.title ?? `${b.bill_type.toUpperCase()} ${b.number}`}</span>
                      <span className="shrink-0 font-mono text-xs text-slate-400">
                        {b.bill_type.toUpperCase()} {b.number}
                      </span>
                    </Row>
                  ))}
                </Group>
              )}
              {results!.votes.length > 0 && (
                <Group label="Votes">
                  {results!.votes.map((v) => (
                    <Row key={v.vote_id} href={`/votes/${v.vote_id}`} onClick={close}>
                      <span className="truncate">{v.question ?? v.vote_id}</span>
                      <span className="shrink-0 text-xs text-slate-400">{v.result ?? ""}</span>
                    </Row>
                  ))}
                </Group>
              )}
              {results!.committees.length > 0 && (
                <Group label="Committees">
                  {results!.committees.map((c) => (
                    <Row key={c.committee_id} href={`/committees/${c.committee_id}`} onClick={close}>
                      <span className="truncate">{c.name}</span>
                    </Row>
                  ))}
                </Group>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="border-b border-slate-100 py-1 last:border-b-0">
      <p className="px-4 py-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
        {label}
      </p>
      {children}
    </div>
  );
}

function Row({
  href,
  onClick,
  children,
}: {
  href: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className="flex items-center justify-between gap-3 px-4 py-2 text-sm hover:bg-slate-50"
    >
      {children}
    </Link>
  );
}
