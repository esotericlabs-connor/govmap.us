import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

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
import { FinanceCard } from "@/components/FinanceCard";
import { MemberAvatar } from "@/components/MemberAvatar";
import { PageSkeleton } from "@/components/PageSkeleton";
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

async function MemberDetailContent({ bioguide }: { bioguide: string }) {
  const member = await getMember(bioguide);
  if (!member) notFound();

  const contact: Record<string, string> = member.contact ?? {};
  const idBadges: [string, string | number][] = [];
  if (member.ids.fec?.length) idBadges.push(["FEC", member.ids.fec[0]]);
  if (member.ids.opensecrets) idBadges.push(["OpenSecrets", member.ids.opensecrets]);
  if (member.ids.govtrack) idBadges.push(["GovTrack", member.ids.govtrack]);
  if (member.ids.lis) idBadges.push(["LIS", member.ids.lis]);
  idBadges.push(["Bioguide", member.bioguide_id]);

  return (
    <Reveal>
      {/* Header */}
      <header className="relative mt-6">
        <div className="flex flex-col items-start gap-8 sm:flex-row">
          <MemberAvatar src={member.photo_url} name={member.official_full_name} size="2xl" />
          <div className="min-w-0 flex-1 pt-2">
            <div className="flex items-center gap-2 text-base font-semibold">
              <span className={`h-2.5 w-2.5 rounded-full ${partyDotClass(member.party)}`} />
              <span className={partyTextClass(member.party)}>{member.party}</span>
            </div>
            <h1 className="mt-1 font-display text-4xl font-bold tracking-tight text-govnavy sm:text-5xl">
              {member.official_full_name}
            </h1>
            <p className="mt-2 text-xl text-slate-warm-500">{seatLabel(member)}</p>
          </div>
          {member.leadership_role && (
            <div className="absolute right-0 top-0 rounded-full bg-govnavy px-4 py-1.5 text-sm font-semibold text-white">
              {member.leadership_role}
            </div>
          )}
        </div>
      </header>

      <div className="mt-12 space-y-10">
        {/* Stat grid */}
        <Section title="Info">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-8 md:grid-cols-4">
            {(member.served_since ?? member.term_start) && (
              <Stat label="In office since">
                {formatDate(member.served_since ?? member.term_start)}
              </Stat>
            )}
            {member.birthday && <Stat label="Born">{formatDate(member.birthday)}</Stat>}
            {contact.office && <Stat label="Office">{contact.office}</Stat>}
            {contact.phone && <Stat label="Phone">{contact.phone}</Stat>}
            {contact.url && (
              <Stat label="Website">
                <a
                  href={contact.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-govblue underline-offset-2 transition-colors hover:text-govblue-600 hover:underline"
                >
                  Official site ↗
                </a>
              </Stat>
            )}
          </dl>
        </Section>

        {/* Campaign finance (only once the FEC pipeline has data) */}
        {member.finance && <FinanceCard finance={member.finance} />}

        {/* Data sections */}
        <div className="grid grid-cols-1 gap-10 lg:grid-cols-2">
          <Section title="Committee Assignments" count={member.committees.length}>
            {member.committees.length === 0 ? (
              <EmptyState>No committee assignments on record.</EmptyState>
            ) : (
              <ul className="-my-3 divide-y divide-slate-warm-100">
                {member.committees.map((c) => (
                  <li key={c.committee_id} className="flex items-center justify-between gap-4 py-3">
                    <Link
                      href={`/committees/${c.committee_id}`}
                      className="font-semibold text-slate-800 transition-colors hover:text-govblue"
                    >
                      {c.name}
                    </Link>
                    {c.role && (
                      <span className="flex-shrink-0 rounded-full bg-slate-warm-100 px-2.5 py-1 text-xs font-semibold text-slate-warm-600">
                        {c.role}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Sponsored Bills" count={member.sponsored_bills_total}>
            {member.sponsored_bills.length === 0 ? (
              <EmptyState>No bills sponsored in the current Congress.</EmptyState>
            ) : (
              <ul className="-my-3 divide-y divide-slate-warm-100">
                {member.sponsored_bills.map((b) => (
                  <li key={b.bill_id} className="py-3.5">
                    <Link href={`/bills/${b.bill_id}`} className="group block">
                      <p className="font-semibold text-slate-800 transition-colors group-hover:text-govblue">
                        {b.title ?? `${b.bill_type.toUpperCase()} ${b.number}`}
                      </p>
                      <div className="mt-1.5 flex items-center gap-3">
                        <CodePill>{`${b.bill_type.toUpperCase()} ${b.number}`}</CodePill>
                        {b.introduced_date && (
                          <p className="text-sm text-slate-warm-500">
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

        <Section title="Recent Voting Record" count={member.voting_record.length}>
          {member.voting_record.length === 0 ? (
            <EmptyState>No votes loaded yet for this member.</EmptyState>
          ) : (
            <ul className="-my-2 divide-y divide-slate-warm-100">
              {member.voting_record.map((v) => (
                <li
                  key={v.vote_id}
                  className="flex flex-wrap items-center justify-between gap-4 py-3"
                >
                  <Link href={`/votes/${v.vote_id}`} className="group min-w-0">
                    <p className="font-semibold text-slate-800 transition-colors group-hover:text-govblue">
                      {v.question ?? v.vote_id}
                    </p>
                    <p className="mt-0.5 text-sm text-slate-warm-500">
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

      {/* Source IDs — provenance, kept at the bottom (not front-and-center). */}
      <div className="mt-12 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-warm-200 pt-6">
        <p className="text-sm font-semibold text-slate-warm-400">Source IDs</p>
        {idBadges.map(([label, value]) => (
          <span key={label} className="text-sm text-slate-warm-500">
            <CodePill>
              {label}: {value}
            </CodePill>
          </span>
        ))}
      </div>
    </Reveal>
  );
}

export default function MemberDetailPage({ params }: { params: { bioguide: string } }) {
  return (
    <>
      <SiteHeader variant="app" />
      <main className="bg-slate-warm-50 pb-20 pt-28">
        <div className="mx-auto max-w-6xl px-6">
          <BackLink href="/members">All Members</BackLink>
          <Suspense fallback={<PageSkeleton />}>
            <MemberDetailContent bioguide={params.bioguide} />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
