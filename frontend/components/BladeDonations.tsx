"use client";

import { useEffect, useState } from "react";

import { DonationsLedger } from "@/components/DonationsLedger";
import {
  fetchDonationCycles,
  publicApiBase,
  type DonationsResponse,
  type MemberDetail,
} from "@/lib/api";

const PAGE_SIZE = 50;

/**
 * Itemized-donations ledger rendered *inside* the member blade — a sub-view, not
 * a route change, so the map underneath is never remounted (and never snaps back
 * to the user's home reps). Fetches the first page and the member's available
 * FEC cycles client-side in parallel, then hands off to the shared
 * `DonationsLedger` with `urlSync={false}` — the blade owns the `?member=` URL,
 * so the ledger must not fight it with its own `?cycle=`/`?sort=` history writes.
 */
export function BladeDonations({
  member,
  onBack,
}: {
  member: MemberDetail;
  onBack: () => void;
}) {
  const bioguide = member.bioguide_id;
  const [state, setState] = useState<{ data: DonationsResponse; cycles: number[] } | null>(null);
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    let alive = true;
    setState(null);
    setErrored(false);
    Promise.all([
      fetch(
        `${publicApiBase}/api/members/${encodeURIComponent(bioguide)}/donations?limit=${PAGE_SIZE}&sort=amount`,
      ).then((r) =>
        r.ok
          ? (r.json() as Promise<DonationsResponse>)
          : Promise.reject(new Error(String(r.status))),
      ),
      fetchDonationCycles(bioguide),
    ])
      .then(([data, cycles]) => {
        if (alive) setState({ data, cycles });
      })
      .catch(() => {
        if (alive) setErrored(true);
      });
    return () => {
      alive = false;
    };
  }, [bioguide]);

  return (
    <div>
      <button
        type="button"
        onClick={onBack}
        className="mb-6 inline-flex items-center gap-1.5 text-sm font-semibold text-slate-warm-600 transition-colors hover:text-govnavy"
      >
        <span aria-hidden="true">←</span> {member.official_full_name}
      </button>

      {errored ? (
        <p className="mt-10 text-center text-sm text-slate-warm-500">
          These contributions couldn&rsquo;t be loaded.{" "}
          <a
            href={`/members/${bioguide}/donations`}
            className="font-semibold text-govblue hover:text-govnavy"
          >
            Open the full page ↗
          </a>
        </p>
      ) : state ? (
        <DonationsLedger
          bioguide={bioguide}
          initialCycle={state.data.cycle}
          cycles={state.cycles}
          initial={state.data}
          initSort="amount"
          initQ=""
          initOffset={0}
          urlSync={false}
        />
      ) : (
        <DonationsSkeleton />
      )}
    </div>
  );
}

function DonationsSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-10 w-full rounded-full bg-slate-warm-200" />
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-center justify-between gap-4 py-2">
          <div className="space-y-2">
            <div className="h-4 w-40 rounded bg-slate-warm-200" />
            <div className="h-3 w-28 rounded bg-slate-warm-200" />
          </div>
          <div className="h-5 w-16 rounded bg-slate-warm-200" />
        </div>
      ))}
    </div>
  );
}
