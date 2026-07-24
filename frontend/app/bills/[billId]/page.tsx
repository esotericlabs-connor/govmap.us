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
  Section,
} from "@/components/DetailKit";
import { MemberAvatar } from "@/components/MemberAvatar";
import { PageSkeleton } from "@/components/PageSkeleton";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { apiGet, HttpError, type BillDetail } from "@/lib/api";

export const dynamic = "force-dynamic";

async function getBill(billId: string): Promise<BillDetail | null> {
  try {
    return await apiGet<BillDetail>(`/api/bills/${encodeURIComponent(billId)}`);
  } catch (err) {
    if (err instanceof HttpError && err.status === 404) return null;
    throw err;
  }
}

export async function generateMetadata({ params }: { params: { billId: string } }) {
  const bill = await getBill(params.billId).catch(() => null);
  const label = bill ? `${bill.bill_type.toUpperCase()} ${bill.number}` : "Bill";
  return { title: bill?.title ?? label };
}

function StatusPill({ status }: { status: string | null }) {
  if (!status) return null;
  // A simple heuristic for status color. Could be expanded.
  const norm = status.toLowerCase();
  const isGood = norm.includes("law") || norm.includes("agreed to");
  const color = isGood
    ? "bg-green-100/80 text-green-800 ring-green-600/30"
    : "bg-slate-warm-100 text-slate-warm-700 ring-slate-600/20";

  return (
    <p
      className={`inline-block rounded-full px-3 py-1 text-xs font-bold ring-1 ring-inset ${color}`}
    >
      {status}
    </p>
  );
}

async function BillDetailContent({ billId }: { billId: string }) {
  const bill = await getBill(billId);
  if (!bill) notFound();

  const label = `${bill.bill_type.toUpperCase()} ${bill.number}`;

  return (
    <Reveal>
      <header className="mt-6">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <CodePill>{label}</CodePill>
          {bill.congress && (
            <p className="text-sm font-medium text-slate-warm-500">{bill.congress}th Congress</p>
          )}
          <StatusPill status={bill.status} />
        </div>
        <h1 className="mt-3 font-display text-4xl font-bold tracking-tight text-govnavy sm:text-5xl">
          {bill.title ?? label}
        </h1>
        {bill.latest_action && (
          <div className="mt-6 rounded-lg border border-slate-warm-200 bg-slate-warm-100/70 p-4">
            <p className="font-semibold text-slate-warm-600">
              Latest action ({formatDate(bill.latest_action_date)})
            </p>
            <p className="mt-1 text-slate-800">{bill.latest_action}</p>
          </div>
        )}
      </header>

      <div className="mt-12 grid grid-cols-1 gap-10 lg:grid-cols-3">
        {/* Main content: summary + timeline */}
        <div className="lg:col-span-2">
          <div className="space-y-10">
            {(bill.summary || bill.text_url) && (
              <Section title="What this bill does">
                {bill.summary ? (
                  <p className="whitespace-pre-line leading-relaxed text-slate-warm-700">
                    {bill.summary}
                  </p>
                ) : (
                  <EmptyState>No plain-English summary published yet for this bill.</EmptyState>
                )}
                {bill.text_url && (
                  <a
                    href={bill.text_url}
                    target="_blank"
                    rel="noreferrer"
                    className="group mt-6 inline-flex items-center gap-1.5 self-start rounded-full bg-govnavy px-5 py-2.5 text-sm font-semibold text-white transition-all duration-200 hover:-translate-y-px hover:bg-govnavy/90"
                  >
                    Read full text {bill.text_version && `(${bill.text_version})`}
                    <span className="transition-transform group-hover:translate-x-0.5">↗</span>
                  </a>
                )}
                {bill.summary && (
                  <p className="mt-4 text-xs text-slate-warm-400">
                    Summary by the Congressional Research Service
                    {bill.summary_date ? ` · ${formatDate(bill.summary_date)}` : ""}
                  </p>
                )}
              </Section>
            )}

            <Section title="Action Timeline" count={bill.actions.length}>
              {bill.actions.length === 0 ? (
                <EmptyState>No actions found for this bill.</EmptyState>
              ) : (
                <ol className="relative -ml-1 border-l-2 border-slate-warm-200">
                  {bill.actions.map((a, i) => (
                    <li key={a.seq} className="mb-6 ml-6">
                      <span
                        className={`absolute -left-[9px] flex h-4 w-4 items-center justify-center rounded-full ring-8 ring-white ${
                          i === 0 ? "bg-govblue" : "bg-slate-warm-300"
                        }`}
                      />
                      <div className="rounded-lg border border-slate-warm-200 bg-white p-4 shadow-sm">
                        <p className="text-sm font-semibold text-slate-warm-600">
                          {a.action_date ? formatDate(a.action_date) : "Date not specified"}
                          {a.chamber && ` · ${chamberLabel(a.chamber)}`}
                        </p>
                        <p className="mt-1 text-slate-800">{a.text}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </Section>
          </div>
        </div>

        {/* Sidebar: sponsor + cosponsors */}
        <aside className="space-y-10">
          {bill.sponsor && (
            <Section title="Sponsor">
              <Link
                href={`/members/${bill.sponsor.bioguide_id}`}
                className="group -m-3 block rounded-lg p-3 transition-colors hover:bg-slate-warm-50"
              >
                <div className="flex items-center gap-4">
                  <MemberAvatar
                    src={bill.sponsor.photo_url}
                    name={bill.sponsor.official_full_name ?? ""}
                    size="md"
                  />
                  <div className="min-w-0">
                    <p className="font-semibold text-govnavy transition-colors group-hover:text-govblue-600">
                      {bill.sponsor.official_full_name}
                    </p>
                    <p className="flex items-center gap-1.5 text-sm">
                      <span
                        className={`h-2 w-2 rounded-full ${partyDotClass(bill.sponsor.party)}`}
                      />
                      <span className={partyTextClass(bill.sponsor.party)}>
                        {bill.sponsor.party}
                      </span>
                      <span className="text-slate-warm-400">· {bill.sponsor.state}</span>
                    </p>
                  </div>
                </div>
              </Link>
            </Section>
          )}

          <Section title="Cosponsors" count={bill.cosponsors.length}>
            {bill.cosponsors.length === 0 ? (
              <EmptyState>No cosponsors on this bill.</EmptyState>
            ) : (
              <ul className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2 lg:grid-cols-1">
                {bill.cosponsors.map((c) => (
                  <li key={c.bioguide_id}>
                    <Link
                      href={`/members/${c.bioguide_id}`}
                      className="group inline-flex items-start gap-2 text-sm"
                    >
                      <span
                        className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${partyDotClass(
                          c.party,
                        )}`}
                      />
                      <span className="font-medium text-slate-warm-700 transition-colors group-hover:text-govblue-600">
                        {c.official_full_name}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </aside>
      </div>
    </Reveal>
  );
}

export default function BillDetailPage({ params }: { params: { billId: string } }) {
  return (
    <>
      <SiteHeader variant="app" />
      <main className="bg-slate-warm-50 pb-20 pt-28">
        <div className="mx-auto max-w-6xl px-6">
          <BackLink href="/bills">All Bills</BackLink>
          <Suspense fallback={<PageSkeleton />}>
            <BillDetailContent billId={params.billId} />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
