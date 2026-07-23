"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { partyDotClass, partyTextClass } from "@/components/DetailKit";
import { MemberAvatar } from "@/components/MemberAvatar";
import { publicApiBase, type LookupMember, type LookupResult } from "@/lib/api";

/**
 * "Find your representatives" ZIP lookup. Posts the 5-digit ZIP to /api/lookup
 * and renders the matched senators + House representative(s) as linked cards.
 * Validation is client-side (5 digits) and mirrored server-side. `onResult`
 * lets a parent (the map) highlight the matched district(s); it's optional so
 * the component is usable standalone.
 */

function seatLabel(m: LookupMember): string {
  if (m.chamber === "senate") return `${m.state} · U.S. Senate`;
  const where = m.district && m.district > 0 ? `${m.state}-${m.district}` : `${m.state} At-Large`;
  return `${where} · U.S. House`;
}

function MemberResultCard({ m }: { m: LookupMember }) {
  return (
    <Link
      href={`/members/${m.bioguide_id}`}
      className="group flex items-center gap-4 rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-govblue hover:shadow-card"
    >
      <MemberAvatar src={m.photo_url} name={m.official_full_name} size="md" />
      <div className="min-w-0">
        <p className="truncate font-semibold text-govnavy group-hover:text-govblue">
          {m.official_full_name}
        </p>
        <p className="mt-0.5 flex items-center gap-1.5 text-sm text-slate-500">
          <span className={`h-2 w-2 shrink-0 rounded-full ${partyDotClass(m.party)}`} />
          <span className={partyTextClass(m.party)}>{m.party}</span>
        </p>
        <p className="mt-0.5 text-xs text-slate-400">{seatLabel(m)}</p>
      </div>
    </Link>
  );
}

export function ZipLookup({
  onResult,
  className = "",
}: {
  onResult?: (result: LookupResult | null) => void;
  className?: string;
}) {
  const [zip, setZip] = useState("");
  const [result, setResult] = useState<LookupResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const z = zip.trim();
    if (!/^\d{5}$/.test(z)) {
      setError("Enter a valid 5-digit ZIP code.");
      setResult(null);
      onResult?.(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${publicApiBase}/api/lookup?zip=${z}`);
      if (!res.ok) throw new Error(String(res.status));
      const data = (await res.json()) as LookupResult;
      if (data.senators.length === 0 && data.representatives.length === 0) {
        setError(`We couldn't match ZIP ${z} to a district yet.`);
        setResult(null);
        onResult?.(null);
      } else {
        setResult(data);
        onResult?.(data);
      }
    } catch {
      setError("Lookup failed — please try again in a moment.");
      setResult(null);
      onResult?.(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={className}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3 sm:flex-row">
        <label htmlFor="zip-lookup" className="sr-only">
          ZIP code
        </label>
        <input
          id="zip-lookup"
          type="text"
          inputMode="numeric"
          autoComplete="postal-code"
          maxLength={5}
          value={zip}
          onChange={(e) => setZip(e.target.value.replace(/\D/g, "").slice(0, 5))}
          placeholder="Enter your ZIP code"
          aria-label="Enter your ZIP code"
          className="w-full rounded-full border border-white/25 bg-white/10 px-5 py-3 text-white placeholder:text-white/50 outline-none backdrop-blur-sm transition focus:border-white/60 focus:bg-white/20 sm:w-56"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-full bg-govblue px-6 py-3 font-semibold text-govnavy shadow-lg shadow-govblue/30 transition hover:-translate-y-0.5 hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Finding…" : "Find my reps"}
        </button>
      </form>

      {error && <p className="mt-3 text-sm font-medium text-govred">{error}</p>}

      {result && (
        <div className="mt-6 space-y-6">
          {result.senators.length > 0 && (
            <div>
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-white/70">
                Your Senators
              </h3>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {result.senators.map((m) => (
                  <MemberResultCard key={m.bioguide_id} m={m} />
                ))}
              </div>
            </div>
          )}
          {result.representatives.length > 0 && (
            <div>
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-white/70">
                Your Representative{result.representatives.length > 1 ? "s" : ""}
              </h3>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {result.representatives.map((m) => (
                  <MemberResultCard key={m.bioguide_id} m={m} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
