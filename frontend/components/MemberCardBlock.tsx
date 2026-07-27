"use client";

import { useEffect, useState } from "react";

import { MemberAvatar } from "@/components/MemberAvatar";
import { MemberLink } from "@/components/MemberLink";
import { fetchMemberCard, type MemberCard } from "@/lib/api";

type Party = "D" | "R" | "I";

const PARTY_NAME: Record<Party, string> = {
  D: "Democrat",
  R: "Republican",
  I: "Independent",
};

const PARTY_DOT: Record<Party, string> = {
  D: "bg-govblue",
  R: "bg-govred",
  I: "bg-slate-400",
};

// ISO date -> the four-digit year, for the compact "since" stat.
function tenureYear(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const m = /^(\d{4})/.exec(iso);
  return m ? m[1] : null;
}

function Stat({ label, value, loading }: { label: string; value: string; loading: boolean }) {
  return (
    <div className="rounded-lg bg-slate-warm-50 px-2 py-1.5 text-center">
      <p
        className={`text-sm font-bold tabular-nums text-govnavy ${loading ? "animate-pulse text-slate-warm-300" : ""}`}
      >
        {value}
      </p>
      <p className="mt-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-warm-400">
        {label}
      </p>
    </div>
  );
}

/**
 * One member as a rich, clickable block inside the map's info card. Seeds
 * instantly from the name/party the map already holds, then fills in the
 * portrait, tenure, and rolling 90-day activity once the card endpoint resolves.
 * The whole block links to the full member profile.
 */
export function MemberCardBlock({
  bioguide,
  name,
  party,
  role,
}: {
  bioguide: string;
  name: string;
  party: Party;
  role: string;
}) {
  const [card, setCard] = useState<MemberCard | null>(null);

  useEffect(() => {
    let alive = true;
    setCard(null);
    fetchMemberCard(bioguide, 90).then((c) => {
      if (alive) setCard(c);
    });
    return () => {
      alive = false;
    };
  }, [bioguide]);

  const displayName = card?.official_full_name ?? name;
  const since = tenureYear(card?.served_since);
  const loading = card === null;
  const windowLabel = `${card?.activity_window_days ?? 90}d`;

  return (
    <MemberLink
      bioguide={bioguide}
      className="group block rounded-xl border border-slate-warm-200 p-3 transition-colors hover:border-govblue/60 hover:bg-slate-warm-50"
    >
      <div className="flex items-center gap-3">
        <MemberAvatar src={card?.photo_url ?? null} name={displayName} size="md" />
        <div className="min-w-0">
          <p className="truncate font-semibold text-govnavy">{displayName}</p>
          <p className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-warm-500">
            <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${PARTY_DOT[party]}`} />
            <span className="truncate">
              {PARTY_NAME[party]} · {role}
            </span>
          </p>
          {card?.leadership_role && (
            <p className="mt-0.5 truncate text-[11px] font-medium text-govblue">
              {card.leadership_role}
            </p>
          )}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-1.5">
        <Stat label="Since" value={since ?? "—"} loading={loading} />
        <Stat label={`Bills · ${windowLabel}`} value={loading ? "—" : String(card?.recent_bills ?? 0)} loading={loading} />
        <Stat label={`Votes · ${windowLabel}`} value={loading ? "—" : String(card?.recent_votes ?? 0)} loading={loading} />
      </div>

      <span className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-govblue transition-colors group-hover:text-govnavy">
        View full profile
        <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5">
          →
        </span>
      </span>
    </MemberLink>
  );
}
