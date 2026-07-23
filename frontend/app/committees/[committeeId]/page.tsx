import Link from "next/link";
import { notFound } from "next/navigation";

import {
  BackLink,
  chamberLabel,
  EmptyState,
  partyTextClass,
  Section,
} from "@/components/DetailKit";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { apiGet, HttpError, type CommitteeDetail } from "@/lib/api";

export const dynamic = "force-dynamic";

async function getCommittee(id: string): Promise<CommitteeDetail | null> {
  try {
    return await apiGet<CommitteeDetail>(`/api/committees/${encodeURIComponent(id)}`);
  } catch (err) {
    if (err instanceof HttpError && err.status === 404) return null;
    throw err;
  }
}

export async function generateMetadata({ params }: { params: { committeeId: string } }) {
  const committee = await getCommittee(params.committeeId).catch(() => null);
  return { title: committee ? committee.name : "Committee" };
}

export default async function CommitteeDetailPage({
  params,
}: {
  params: { committeeId: string };
}) {
  const committee = await getCommittee(params.committeeId);
  if (!committee) notFound();

  const majority = committee.members.filter((m) => m.side === "majority");
  const minority = committee.members.filter((m) => m.side === "minority");
  const other = committee.members.filter((m) => m.side !== "majority" && m.side !== "minority");

  const roster = (rows: CommitteeDetail["members"]) => (
    <ul className="space-y-1.5">
      {rows.map((m) => (
        <li key={m.bioguide_id} className="flex items-center justify-between gap-2">
          <Link
            href={`/members/${m.bioguide_id}`}
            className={`text-sm hover:underline ${partyTextClass(m.party)}`}
          >
            {m.official_full_name}
            <span className="text-slate-400"> · {m.state}</span>
          </Link>
          {m.role && <span className="shrink-0 text-xs font-medium text-slate-400">{m.role}</span>}
        </li>
      ))}
    </ul>
  );

  return (
    <>
      <SiteHeader variant="app" />
      <main className="min-h-screen bg-slate-50 pb-16 pt-24">
        <div className="mx-auto max-w-4xl px-6 py-6">
          <BackLink href="/members">Back</BackLink>

          <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-card">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
              {chamberLabel(committee.chamber)} committee
            </p>
            <h1 className="mt-1 font-display text-2xl font-bold text-govnavy">{committee.name}</h1>
            {committee.parent_committee_id && (
              <Link
                href={`/committees/${committee.parent_committee_id}`}
                className="mt-2 inline-block text-sm text-govblue hover:underline"
              >
                ← Parent committee
              </Link>
            )}
            {committee.url && (
              <a
                href={committee.url}
                target="_blank"
                rel="noreferrer"
                className="mt-2 block text-xs text-govblue hover:underline"
              >
                Official page ↗
              </a>
            )}
          </div>

          {committee.members.length === 0 ? (
            <div className="mt-6">
              <Section title="Members">
                <EmptyState>No membership loaded for this committee.</EmptyState>
              </Section>
            </div>
          ) : (
            <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
              {majority.length > 0 && (
                <Section title="Majority" count={majority.length}>
                  {roster(majority)}
                </Section>
              )}
              {minority.length > 0 && (
                <Section title="Minority" count={minority.length}>
                  {roster(minority)}
                </Section>
              )}
              {other.length > 0 && (
                <Section title="Members" count={other.length}>
                  {roster(other)}
                </Section>
              )}
            </div>
          )}
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
