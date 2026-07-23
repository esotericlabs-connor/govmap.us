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
  const idBadges: [string, string][] = [];
  if (member.ids.fec?.length) idBadges.push(["FEC", member.ids.fec[0]]);
  if (member.ids.opensecrets) idBadges.push(["OpenSecrets", member.ids.opensecrets]);
  if (member.ids.govtrack) idBadges.push(["GovTrack", String(member.ids.govtrack)]);
  if (member.ids.lis) idBadges.push(["LIS", member.ids.lis]);
  idBadges.push(["Bioguide", member.bioguide_id]);

  return (
    <>
      <SiteHeader variant="app" />
      <main className="min-h-screen bg-slate-50 pb-16 pt-24">
        <div className="mx-auto max-w-4xl px-6 py-6">
          <BackLink href="/members">All members</BackLink>

          {/* Header */}
          <div className="mt-4 flex flex-col gap-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-card sm:flex-row sm:items-center">
            <MemberAvatar src={member.photo_url} name={member.official_full_name} size="xl" />
            <div className="min-w-0">
              <h1 className="font-display text-3xl font-bold text-govnavy">
                {member.official_full_name}
              </h1>
              <p className="mt-1 flex flex-wrap items-center gap-2 text-slate-600">
                <span className={`inline-block h-2.5 w-2.5 rounded-full ${partyDotClass(member.party)}`} />
                <span className={`font-semibold ${partyTextClass(member.party)}`}>{member.party}</span>
                <span className="text-slate-300">·</span>
                <span>{seatLabel(member)}</span>
              </p>
              {member.leadership_role && (
                <p className="mt-2 inline-block rounded-full bg-govnavy px-3 py-1 text-xs font-semibold text-white">
                  {member.leadership_role}
                </p>
              )}
            </div>
          </div>

          {/* Bio + contact */}
          <div className="mt-6">
            <Section title="Profile">
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
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
                      className="text-govblue hover:underline"
                    >
                      Official site
                    </a>
                  </Stat>
                )}
              </dl>
              <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
                {idBadges.map(([label, value]) => (
                  <span key={label} className="text-xs text-slate-500">
                    <span className="font-medium text-slate-400">{label}</span> <CodePill>{value}</CodePill>
                  </span>
                ))}
              </div>
            </Section>
          </div>

          {/* Data sections */}
          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Section title="Committees" count={member.committees.length}>
              {member.committees.length === 0 ? (
                <EmptyState>No committee assignments on record.</EmptyState>
              ) : (
                <ul className="space-y-2">
                  {member.committees.map((c) => (
                    <li key={c.committee_id} className="flex items-start justify-between gap-3">
                      <Link
                        href={`/committees/${c.committee_id}`}
                        className="text-sm text-slate-800 hover:text-govblue"
                      >
                        {c.name}
                      </Link>
                      {c.role && (
                        <span className="shrink-0 text-xs font-medium text-slate-400">{c.role}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title="Sponsored bills" count={member.sponsored_bills.length}>
              {member.sponsored_bills.length === 0 ? (
                <EmptyState>No sponsored bills loaded yet.</EmptyState>
              ) : (
                <ul className="space-y-3">
                  {member.sponsored_bills.map((b) => (
                    <li key={b.bill_id}>
                      <Link href={`/bills/${b.bill_id}`} className="group block">
                        <span className="text-sm font-medium text-slate-800 group-hover:text-govblue">
                          {b.title ?? `${b.bill_type.toUpperCase()} ${b.number}`}
                        </span>
                        <span className="mt-0.5 flex items-center gap-2 text-xs text-slate-400">
                          <CodePill>{`${b.bill_type.toUpperCase()} ${b.number}`}</CodePill>
                          {b.introduced_date && <span>Introduced {formatDate(b.introduced_date)}</span>}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>

          <div className="mt-6">
            <Section title="Recent votes" count={member.voting_record.length}>
              {member.voting_record.length === 0 ? (
                <EmptyState>No votes loaded yet for this member.</EmptyState>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {member.voting_record.map((v) => (
                    <li key={v.vote_id} className="flex items-center justify-between gap-3 py-2.5">
                      <Link href={`/votes/${v.vote_id}`} className="min-w-0 group">
                        <span className="block truncate text-sm text-slate-800 group-hover:text-govblue">
                          {v.question ?? v.vote_id}
                        </span>
                        <span className="text-xs text-slate-400">
                          {chamberLabel(v.chamber)}
                          {v.date && ` · ${formatDate(v.date)}`}
                          {v.result && ` · ${v.result}`}
                        </span>
                      </Link>
                      <PositionPill position={v.position} />
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
