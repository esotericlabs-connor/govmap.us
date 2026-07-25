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
import { SiteHeader } from "@/components/SiteHeader";
import {
  apiGet,
  HttpError,
  type CommitteeDetail,
  type CommitteeMeeting,
  type CommitteeMember,
  type CommitteeReferredBills,
} from "@/lib/api";

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

// Committee meetings run on Eastern time; format the UTC datetime in ET so the
// date/time read as scheduled.
const MEETING_FMT = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZone: "America/New_York",
  timeZoneName: "short",
});

function meetingWhen(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : MEETING_FMT.format(d);
}

function billLabel(billId: string): string {
  const m = billId.match(/^([a-z]+)(\d+)-/i);
  return m ? `${m[1].toUpperCase()} ${m[2]}` : billId;
}

function MeetingCard({ meeting, upcoming = false }: { meeting: CommitteeMeeting; upcoming?: boolean }) {
  const when = meetingWhen(meeting.datetime);
  const off = meeting.status ? /cancel|postpon/i.test(meeting.status) : false;
  return (
    <div className="rounded-lg border border-slate-warm-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {meeting.meeting_type && (
          <span className="rounded-full bg-slate-warm-100 px-2.5 py-0.5 text-xs font-semibold text-slate-warm-600">
            {meeting.meeting_type}
          </span>
        )}
        {when && (
          <span
            className={`text-sm font-semibold ${upcoming ? "text-govblue-600" : "text-slate-warm-500"}`}
          >
            {when}
          </span>
        )}
        {off && (
          <span className="rounded-full bg-red-100/80 px-2 py-0.5 text-xs font-semibold text-red-700">
            {meeting.status}
          </span>
        )}
      </div>
      {meeting.title && <p className="mt-2 font-medium text-slate-800">{meeting.title}</p>}
      {meeting.location && <p className="mt-1 text-sm text-slate-warm-500">{meeting.location}</p>}
      {meeting.bill_ids.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {meeting.bill_ids.map((bid) => (
            <Link
              key={bid}
              href={`/bills/${bid}`}
              className="rounded-md bg-slate-warm-100 px-2 py-1 font-mono text-xs font-medium text-govblue transition-colors hover:text-govblue-600"
            >
              {billLabel(bid)}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

async function getReferredBills(committeeId: string): Promise<CommitteeReferredBills | null> {
  // Fail-soft: on any error the section is simply omitted.
  try {
    return await apiGet<CommitteeReferredBills>(
      `/api/committees/${encodeURIComponent(committeeId)}/bills`,
    );
  } catch {
    return null;
  }
}

function ReferredBillsSkeleton() {
  return (
    <Section title="Recent bills before this committee">
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-16 w-full animate-pulse rounded-lg bg-slate-warm-100" />
        ))}
      </div>
    </Section>
  );
}

// Streamed in its own Suspense boundary — the first request fetches referrals
// from Congress.gov, so the rest of the committee page never waits on it.
async function ReferredBills({ committeeId }: { committeeId: string }) {
  const data = await getReferredBills(committeeId);
  if (!data || data.bills.length === 0) return null;
  return (
    <Section title="Recent bills before this committee" count={data.bills.length} scroll>
      <ul className="space-y-3">
        {data.bills.map((b) => (
          <li key={b.bill_id}>
            <Link
              href={`/bills/${b.bill_id}`}
              className="group block rounded-lg border border-slate-warm-200 bg-white p-4 shadow-sm transition-colors hover:border-govblue-400"
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-semibold text-govblue">
                  {billLabel(b.bill_id)}
                </span>
                {b.relationship && (
                  <span className="text-xs text-slate-warm-400">· {b.relationship}</span>
                )}
              </div>
              {b.title && (
                <p className="mt-1 font-medium text-slate-800 transition-colors group-hover:text-govblue-600">
                  {b.title}
                </p>
              )}
              {b.latest_action && (
                <p className="mt-1 line-clamp-1 text-sm text-slate-warm-500">{b.latest_action}</p>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </Section>
  );
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

      {committee.upcoming_meetings.length > 0 && (
        <div className="mt-12">
          <Section title="Upcoming meetings" count={committee.upcoming_meetings.length} scroll>
            <div className="space-y-4">
              {committee.upcoming_meetings.map((m) => (
                <MeetingCard key={m.event_id} meeting={m} upcoming />
              ))}
            </div>
          </Section>
        </div>
      )}

      <div className="mt-12">
        {committee.members.length === 0 ? (
          <Section title="Members">
            <EmptyState>No membership data is available for this committee.</EmptyState>
          </Section>
        ) : (
          <div className="grid grid-cols-1 gap-10 lg:grid-cols-2 lg:gap-16">
            {majority.length > 0 && (
              <Section title="Majority" count={majority.length} scroll>
                <div className="grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2">
                  {majority.map((m) => (
                    <MemberCard key={m.bioguide_id} member={m} />
                  ))}
                </div>
              </Section>
            )}
            {minority.length > 0 && (
              <Section title="Minority" count={minority.length} scroll>
                <div className="grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2">
                  {minority.map((m) => (
                    <MemberCard key={m.bioguide_id} member={m} />
                  ))}
                </div>
              </Section>
            )}
            {other.length > 0 && (
              <div className="lg:col-span-2">
                <Section title="Other Members" count={other.length} scroll>
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

      {committee.subcommittees.length > 0 && (
        <div className="mt-12">
          <Section title="Subcommittees" count={committee.subcommittees.length} scroll>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {committee.subcommittees.map((s) => (
                <Link
                  key={s.committee_id}
                  href={`/committees/${s.committee_id}`}
                  className="rounded-lg border border-slate-warm-200 bg-white p-3 text-sm font-medium text-slate-800 shadow-sm transition-colors hover:border-govblue-400 hover:text-govblue-600"
                >
                  {s.name}
                </Link>
              ))}
            </div>
          </Section>
        </div>
      )}

      <div className="mt-12">
        <Suspense fallback={<ReferredBillsSkeleton />}>
          <ReferredBills committeeId={committeeId} />
        </Suspense>
      </div>

      {committee.recent_meetings.length > 0 && (
        <div className="mt-12">
          <Section title="Recent meetings" count={committee.recent_meetings.length} scroll>
            <div className="space-y-3">
              {committee.recent_meetings.map((m) => (
                <MeetingCard key={m.event_id} meeting={m} />
              ))}
            </div>
          </Section>
        </div>
      )}
    </Reveal>
  );
}

export default function CommitteeDetailPage({ params }: { params: { committeeId: string } }) {
  return (
    <>
      <SiteHeader variant="app" />
      <main className="bg-slate-warm-50 pb-20 pt-28">
        <div className="mx-auto max-w-6xl px-6">
          <BackLink href="/congress">Back to map</BackLink>
          <Suspense fallback={<PageSkeleton />}>
            <CommitteeDetailContent committeeId={params.committeeId} />
          </Suspense>
        </div>
      </main>
    </>
  );
}
