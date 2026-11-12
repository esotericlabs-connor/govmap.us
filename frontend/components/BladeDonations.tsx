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
 * The member panel owns navigation history. Keep this ledger mounted while
 * returning to the same member's profile, so filters and pagination survive.
 */
export function BladeDonations({
  member,
  onReady,
}: {
  member: MemberDetail;
  onReady: () => void;
}) {
  const bioguide = member.bioguide_id;
  const [state, setState] = useState<{ data: DonationsResponse; cycles: number[] } | null>(null);
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    setState(null);
    setErrored(false);
    Promise.all([
      fetch(
        `${publicApiBase}/api/members/${encodeURIComponent(bioguide)}/donations?limit=${PAGE_SIZE}&sort=amount`,
        { signal: controller.signal },
      ).then((r) =>
        r.ok
          ? (r.json() as Promise<DonationsResponse>)
          : Promise.reject(new Error(String(r.status))),
      ),
      fetchDonationCycles(bioguide, controller.signal),
    ])
      .then(([data, cycles]) => {
        if (alive) setState({ data, cycles });
      })
      .catch(() => {
        if (alive) setErrored(true);
      });
    return () => {
      alive = false;
      controller.abort();
    };
  }, [bioguide]);

  useEffect(() => {
    if (state || errored) onReady();
  }, [state, errored, onReady]);

  return (
    <div>
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
