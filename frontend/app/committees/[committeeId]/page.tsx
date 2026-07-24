import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import {
  BackLink,
  chamberLabel,
  EmptyState,
  partyDotClass,
  partyTextClass,
  Section,
} from "@/components/DetailKit";
import { MemberAvatar } from "@/components/MemberAvatar";
import { PageSkeleton } from "@/components/PageSkeleton";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { apiGet, HttpError, type CommitteeDetail, type CommitteeMember } from "@/lib/api";

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
  return { title: committee?.name ?? "Committee" };
}

function MemberCard({ member }: { member: CommitteeMember }) {
  const isChair = member.role?.toLowerCase().includes("chair");
  const isRanking = member.role?.toLowerCase().includes("ranking");

  return (
    <Link
      href={`/members/${member.bioguide_id}`}
      className="group -m-3 block rounded-lg p-3 transition-colors hover:bg-slate-warm-50"
    >
      <div className="flex items-center gap-4">
        <MemberAvatar src={member.photo_url} name={member.official_full_name} size="md" />
        <div className="min-w-0">
          <p className="truncate font-semibold text-govnavy transition-colors group-hover:text-govblue-600">
            {member.official_full_name}
          </p>
          <div className="mt-0.5 flex items-center gap-1.5 text-sm">
            <span className={`h-2 w-2 shrink-0 rounded-full ${partyDotClass(member.party)}`} />
            <span className={partyTextClass(member.party)}>{member.party}</span>
            <span className="text-slate-warm-400">· {member.state}</span>
          </div>
        </div>
      </div>
      {member.role && (
        <div className="mt-3">
          <span
            className={`inline-block rounded-full px-2.5 py-1 text-xs font-semibold ${
              isChair
                ? "bg-govnavy text-white"
                : isRanking
                  ? "bg-white ring-1 ring-inset ring-slate-warm-300"
                  : "bg-slate-warm-100 text-slate-warm-600"
            }`}
          >
            {member.role}
          </span>
        </div>
      )}
    </Link>
  );
}

async function CommitteeDetailContent({ committeeId }: { committeeId: string }) {
  const committee = await getCommittee(committeeId);
  if (!committee) notFound();

  const majority = committee.members.filter((m) => m.side === "majority");
  const minority = committee.members.filter((m) => m.side === "minority");
  const other = committee.members.filter((m) => m.side !== "majority" && m.side !== "minority");

  // Hoist chair/ranking to top
  const sortMembers = (a: CommitteeMember, b: CommitteeMember) => {
    const aRole = a.role?.toLowerCase() ?? "";
    const bRole = b.role?.toLowerCase() ?? "";
    const aIsLeader = aRole.includes("chair") || aRole.includes("ranking");
    const bIsLeader = bRole.includes("chair") || bRole.includes("ranking");
    if (aIsLeader && !bIsLeader) return -1;
    if (!aIsLeader && bIsLeader) return 1;
    return a.official_full_name.localeCompare(b.official_full_name);
  };
  majority.sort(sortMembers);
  minority.sort(sortMembers);
  other.sort(sortMembers);

  return (
    <Reveal>
      <header className="mt-6">
        <p className="font-semibold uppercase tracking-wider text-slate-warm-500">
          {chamberLabel(committee.chamber)} Committee
        </p>
        <h1 className="mt-1 font-display text-4xl font-bold tracking-tight text-govnavy sm:text-5xl">
          {committee.name}
        </h1>
        <div className="mt-4 flex flex-wrap gap-4">
          {committee.url && (
            <a
              href={committee.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-sm font-semibold text-govblue transition-colors hover:text-govblue-600"
            >
              Official Website ↗
            </a>
          )}
          {committee.parent_committee_id && (
            <Link
              href={`/committees/${committee.parent_committee_id}`}
              className="inline-flex items-center gap-1 text-sm font-semibold text-govblue transition-colors hover:text-govblue-600"
            >
              Parent Committee ↑
            </Link>
          )}
        </div>
      </header>

      <div className="mt-12">
        {committee.members.length === 0 ? (
          <Section title="Members">
            <EmptyState>No membership data is available for this committee.</EmptyState>
          </Section>
        ) : (
          <div className="grid grid-cols-1 gap-10 lg:grid-cols-2 lg:gap-16">
            {majority.length > 0 && (
              <Section title="Majority" count={majority.length}>
                <div className="grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2">
                  {majority.map((m) => (
                    <MemberCard key={m.bioguide_id} member={m} />
                  ))}
                </div>
              </Section>
            )}
            {minority.length > 0 && (
              <Section title="Minority" count={minority.length}>
                <div className="grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2">
                  {minority.map((m) => (
                    <MemberCard key={m.bioguide_id} member={m} />
                  ))}
                </div>
              </Section>
            )}
            {other.length > 0 && (
              <div className="lg:col-span-2">
                <Section title="Other Members" count={other.length}>
                  <div className="grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2">
                    {other.map((m) => (
                      <MemberCard key={m.bioguide_id} member={m} />
                    ))}
                  </div>
                </Section>
              </div>
            )}
          </div>
        )}
      </div>
    </Reveal>
  );
}

export default function CommitteeDetailPage({ params }: { params: { committeeId: string } }) {
  return (
    <>
      <SiteHeader variant="app" />
      <main className="bg-slate-warm-50 pb-20 pt-28">
        <div className="mx-auto max-w-6xl px-6">
          <BackLink href="/members">All Members</BackLink>
          <Suspense fallback={<PageSkeleton />}>
            <CommitteeDetailContent committeeId={params.committeeId} />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
