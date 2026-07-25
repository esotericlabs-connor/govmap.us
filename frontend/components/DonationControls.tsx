"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Search + sort controls for a member's itemized-donations ledger. Drives the
 * URL (`q`, `sort`, resets `offset`); the page reads those and re-fetches. The
 * search covers contributor name / employer / city over what's been cached.
 */

const SORTS: { value: string; label: string }[] = [
  { value: "amount", label: "Largest first" },
  { value: "amount_asc", label: "Smallest first" },
  { value: "date", label: "Newest first" },
  { value: "date_asc", label: "Oldest first" },
  { value: "name", label: "Name (A–Z)" },
];

export function DonationControls({ sort, q }: { sort: string; q: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [term, setTerm] = useState(q);

  // Reflect external URL changes (e.g. Back button) into the input.
  useEffect(() => setTerm(q), [q]);

  function push(next: { q?: string; sort?: string }) {
    const params = new URLSearchParams(searchParams.toString());
    if (next.sort !== undefined) params.set("sort", next.sort);
    if (next.q !== undefined) {
      if (next.q) params.set("q", next.q);
      else params.delete("q");
    }
    params.delete("offset"); // any change returns to the first page
    router.push(`${pathname}?${params.toString()}`);
  }

  // Debounce the search → URL push.
  useEffect(() => {
    if (term === q) return;
    const t = setTimeout(() => push({ q: term.trim() }), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [term]);

  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <input
        type="search"
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        placeholder="Search name, employer, or city…"
        aria-label="Search contributions"
        className="w-full rounded-full border border-slate-warm-200 bg-white px-4 py-2.5 text-sm text-slate-800 outline-none focus:border-govblue focus:ring-2 focus:ring-govblue/30 sm:max-w-sm"
      />
      <label className="flex items-center gap-2 whitespace-nowrap text-sm text-slate-warm-500">
        Sort
        <select
          value={sort}
          onChange={(e) => push({ sort: e.target.value })}
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
  );
}
