import Link from "next/link";
import { notFound } from "next/navigation";

import {
  BackLink,
  chamberLabel,
  CodePill,
  EmptyState,
  formatDate,
  partyDotClass,
  partyTextClass,
  PositionPill,
  Section,
  Stat,
} from "@/components/DetailKit";
import { MemberAvatar } from "@/components/MemberAvatar";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { apiGet, HttpError, type MemberDetail } from "@/lib/api";

// Never prerendered — the backend isn't reachable during the image build.
export const dynamic = "force-dynamic";

async function getMember(bioguide: string): Promise<MemberDetail | null> {
  try {
    return await apiGet<MemberDetail>(`/api/members/${encodeURIComponent(bioguide)}`);
  } catch (err) {
    if (err instanceof HttpError && err.status === 404) return null;
    throw err;
  }
}

export async function generateMetadata({ params }: { params: { bioguide: string } }) {
  const member = await getMember(params.bioguide).catch(() => null);
  return { title: member ? member.official_full_name : "Member" };
}

function seatLabel(m: MemberDetail): string {
  const where = m.district !== null ? `${m.state}-${m.district}` : m.state;
  return `${where} · ${chamberLabel(m.chamber)}`;
}

export default async function MemberDetailPage({
  params,
}: {
  params: { bioguide: string };
}) {
  const member = await getMember(params.bioguide);
  if (!member) notFound();

  const contact: Record<string, string> = member.contact ?? {};
  const idBadges: [string, string | number][] = [];
  if (member.ids.fec?.length) idBadges.push(["FEC", member.ids.fec[0]]);
  if (member.ids.opensecrets) idBadges.push(["OpenSecrets", member.ids.opensecrets]);
  if (member.ids.govtrack) idBadges.push(["GovTrack", member.ids.govtrack]);
  if (member.ids.lis) idBadges.push(["LIS", member.ids.lis]);
  idBadges.push(["Bioguide", member.bioguide_id]);

  return (
    <>
      <SiteHeader variant="app" />
      <main className="min-h-screen bg-slate-50 pb-20 pt-24">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
          <BackLink href="/members">All Members</BackLink>

          <Reveal>
            {/* Header */}
            <header className="relative mt-4 flex flex-col items-center gap-8 rounded-xl border border-slate-200/80 bg-white p-8 shadow-card sm:flex-row">
              <MemberAvatar src={member.photo_url} name={member.official_full_name} size="2xl" />
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 text-sm font-medium">
                  <span className={`h-2 w-2 rounded-full ${partyDotClass(member.party)}`} />
                  <span className={partyTextClass(member.party)}>{member.party}</span>
                </p>
                <h1 className="mt-1 font-display text-4xl font-bold tracking-tight text-govnavy">
                  {member.official_full_name}
                </h1>
                <p className="mt-2 text-lg text-slate-500">{seatLabel(member)}</p>
              </div>
              {member.leadership_role && (
                <div className="absolute right-6 top-6 rounded-full bg-govnavy-800 px-3 py-1 text-xs font-semibold text-white/80">
                  {member.leadership_role}
                </div>
              )}
            </header>

            {/* Stat grid */}
            <div className="mt-8">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-8 md:grid-cols-5">
                {member.term_start && <Stat label="In office since">{formatDate(member.term_start)}</Stat>}
                {member.birthday && <Stat label="Born">{formatDate(member.birthday)}</Stat>}
                {contact.office && <Stat label="Office">{contact.office}</Stat>}
                {contact.phone && <Stat label="Phone">{contact.phone}</Stat>}
                {contact.url && (
                  <Stat label="Website">
                    <a
                      href={contact.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-govblue underline-offset-2 hover:underline"
                    >
                      Official site
                    </a>
                  </Stat>
                )}
              </dl>
              <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-200/80 pt-6">
                <p className="text-xs font-medium text-slate-400">Source IDs</p>
                {idBadges.map(([label, value]) => (
                  <span key={label} className="text-xs text-slate-500">
                    <CodePill>
                      {label}: {value}
                    </CodePill>
                  </span>
                ))}
              </div>
            </div>

            {/* Data sections */}
            <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-2">
              <Section title="Committee Assignments" count={member.committees.length}>
                {member.committees.length === 0 ? (
                  <EmptyState>No committee assignments on record.</EmptyState>
                ) : (
                  <ul className="-my-2 divide-y divide-slate-100">
                    {member.committees.map((c) => (
                      <li key={c.committee_id} className="flex items-center justify-between gap-4 py-3">
                        <Link
                          href={`/committees/${c.committee_id}`}
                          className="text-sm font-medium text-slate-800 hover:text-govblue"
                        >
                          {c.name}
                        </Link>
                        {c.role && (
                          <span className="flex-shrink-0 rounded-md bg-slate-50 px-2 py-1 text-xs font-medium text-slate-500">
                            {c.role}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </Section>

              <Section title="Sponsored Bills" count={member.sponsored_bills.length}>
                {member.sponsored_bills.length === 0 ? (
                  <EmptyState>No sponsored bills loaded yet.</EmptyState>
                ) : (
                  <ul className="-my-3 divide-y divide-slate-100">
                    {member.sponsored_bills.map((b) => (
                      <li key={b.bill_id} className="py-3">
                        <Link href={`/bills/${b.bill_id}`} className="group block">
                          <p className="text-sm font-medium text-slate-800 group-hover:text-govblue">
                            {b.title ?? `${b.bill_type.toUpperCase()} ${b.number}`}
                          </p>
                          <div className="mt-1 flex items-center gap-2">
                            <CodePill>{`${b.bill_type.toUpperCase()} ${b.number}`}</CodePill>
                            {b.introduced_date && (
                              <p className="text-xs text-slate-500">
                                Introduced {formatDate(b.introduced_date)}
                              </p>
                            )}
                          </div>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
            </div>

            <div className="mt-8">
              <Section title="Recent Voting Record" count={member.voting_record.length}>
                {member.voting_record.length === 0 ? (
                  <EmptyState>No votes loaded yet for this member.</EmptyState>
                ) : (
                  <ul className="-my-2 divide-y divide-slate-100">
                    {member.voting_record.map((v) => (
                      <li key={v.vote_id} className="flex items-center justify-between gap-4 py-3">
                        <Link href={`/votes/${v.vote_id}`} className="group min-w-0">
                          <p className="truncate text-sm font-medium text-slate-800 group-hover:text-govblue">
                            {v.question ?? v.vote_id}
                          </p>
                          <p className="mt-0.5 text-xs text-slate-500">
                            {chamberLabel(v.chamber)} vote
                            {v.date && ` on ${formatDate(v.date)}`}
                            {v.result && ` (Result: ${v.result})`}
                          </p>
                        </Link>
                        <div className="flex-shrink-0">
                          <PositionPill position={v.position} />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
            </div>
          </Reveal>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
