import Link from "next/link";
import { notFound } from "next/navigation";

import {
  BackLink,
  chamberLabel,
  EmptyState,
  partyDotClass,
  partyTextClass,
  Section,
} from "@/components/DetailKit";
import { MemberAvatar } from "@/components/MemberAvatar";
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
      className={`group block rounded-lg p-3 transition-colors ${
        isChair || isRanking ? "bg-slate-50/80 hover:bg-white" : "hover:bg-slate-50/80"
      }`}
    >
      <div className="flex items-center gap-3">
        <MemberAvatar src={member.photo_url} name={member.official_full_name} size="md" />
        <div className="min-w-0">
          <p className="truncate font-semibold text-slate-800 group-hover:text-govblue">
            {member.official_full_name}
          </p>
          <p className="flex items-center gap-1.5 text-sm">
            <span className={`h-2 w-2 rounded-full ${partyDotClass(member.party)}`} />
            <span className={partyTextClass(member.party)}>{member.party}</span>
            <span className="text-slate-400">· {member.state}</span>
          </p>
        </div>
      </div>
      {member.role && (
        <p
          className={`mt-2 inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${
            isChair
              ? "bg-govnavy text-white"
              : isRanking
                ? "border border-govnavy/50 text-govnavy"
                : "text-slate-500"
          }`}
        >
          {member.role}
        </p>
      )}
    </Link>
  );
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
    <>
      <SiteHeader variant="app" />
      <main className="min-h-screen bg-slate-50 pb-20 pt-24">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
          <BackLink href="/members">All Members</BackLink>

          <Reveal>
            <header className="mt-4 rounded-xl border border-slate-200/80 bg-white p-6 shadow-card">
              <p className="font-semibold uppercase tracking-wider text-slate-500">
                {chamberLabel(committee.chamber)} Committee
              </p>
              <h1 className="mt-1 font-display text-3xl font-bold tracking-tight text-govnavy">
                {committee.name}
              </h1>
              <div className="mt-3 flex gap-4">
                {committee.url && (
                  <a
                    href={committee.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-medium text-govblue underline-offset-2 hover:underline"
                  >
                    Official Website ↗
                  </a>
                )}
                {committee.parent_committee_id && (
                  <Link
                    href={`/committees/${committee.parent_committee_id}`}
                    className="text-sm font-medium text-govblue underline-offset-2 hover:underline"
                  >
                    Parent Committee ↑
                  </Link>
                )}
              </div>
            </header>

            <div className="mt-8">
              {committee.members.length === 0 ? (
                <Section title="Members">
                  <EmptyState>No membership data is available for this committee.</EmptyState>
                </Section>
              ) : (
                <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
                  {majority.length > 0 && (
                    <Section title="Majority" count={majority.length}>
                      <div className="grid grid-cols-1 gap-x-4 gap-y-2 md:grid-cols-2">
                        {majority.map((m) => (
                          <MemberCard key={m.bioguide_id} member={m} />
                        ))}
                      </div>
                    </Section>
                  )}
                  {minority.length > 0 && (
                    <Section title="Minority" count={minority.length}>
                      <div className="grid grid-cols-1 gap-x-4 gap-y-2 md:grid-cols-2">
                        {minority.map((m) => (
                          <MemberCard key={m.bioguide_id} member={m} />
                        ))}
                      </div>
                    </Section>
                  )}
                  {other.length > 0 && (
                    <div className="lg:col-span-2">
                      <Section title="Other Members" count={other.length}>
                        <div className="grid grid-cols-1 gap-x-4 gap-y-2 md:grid-cols-2">
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
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
