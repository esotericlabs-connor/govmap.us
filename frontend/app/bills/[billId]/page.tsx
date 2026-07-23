import Link from "next/link";
import { notFound } from "next/navigation";

import {
  BackLink,
  CodePill,
  EmptyState,
  formatDate,
  partyTextClass,
  Section,
  Stat,
} from "@/components/DetailKit";
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
  return { title: bill ? `${bill.bill_type.toUpperCase()} ${bill.number}` : "Bill" };
}

export default async function BillDetailPage({ params }: { params: { billId: string } }) {
  const bill = await getBill(params.billId);
  if (!bill) notFound();

  const label = `${bill.bill_type.toUpperCase()} ${bill.number}`;

  return (
    <>
      <SiteHeader variant="app" />
      <main className="min-h-screen bg-slate-50 pb-16 pt-24">
        <div className="mx-auto max-w-4xl px-6 py-6">
          <BackLink href="/members">Back</BackLink>

          <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-card">
            <div className="flex flex-wrap items-center gap-2">
              <CodePill>{label}</CodePill>
              <span className="text-xs text-slate-400">{bill.congress}th Congress</span>
              {bill.status && (
                <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
                  {bill.status}
                </span>
              )}
            </div>
            <h1 className="mt-3 font-display text-2xl font-bold text-govnavy">
              {bill.title ?? label}
            </h1>

            <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-slate-100 pt-5 sm:grid-cols-3">
              {bill.sponsor && (
                <Stat label="Sponsor">
                  <Link
                    href={`/members/${bill.sponsor.bioguide_id}`}
                    className={`hover:underline ${partyTextClass(bill.sponsor.party)}`}
                  >
                    {bill.sponsor.official_full_name ?? bill.sponsor.bioguide_id}
                  </Link>
                </Stat>
              )}
              {bill.introduced_date && <Stat label="Introduced">{formatDate(bill.introduced_date)}</Stat>}
              {bill.policy_area && <Stat label="Policy area">{bill.policy_area}</Stat>}
            </dl>

            {bill.latest_action && (
              <div className="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
                <span className="font-medium text-slate-400">Latest action</span>
                {bill.latest_action_date && (
                  <span className="text-slate-400"> · {formatDate(bill.latest_action_date)}</span>
                )}
                <p className="mt-1">{bill.latest_action}</p>
              </div>
            )}
          </div>

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Section title="Action timeline" count={bill.actions.length}>
              {bill.actions.length === 0 ? (
                <EmptyState>No actions loaded.</EmptyState>
              ) : (
                <ol className="space-y-3">
                  {bill.actions.map((a) => (
                    <li key={a.seq} className="border-l-2 border-slate-200 pl-3">
                      <p className="text-xs text-slate-400">
                        {a.action_date ? formatDate(a.action_date) : "—"}
                        {a.chamber && ` · ${a.chamber}`}
                      </p>
                      <p className="text-sm text-slate-700">{a.text}</p>
                    </li>
                  ))}
                </ol>
              )}
            </Section>

            <Section title="Cosponsors" count={bill.cosponsors.length}>
              {bill.cosponsors.length === 0 ? (
                <EmptyState>No cosponsors.</EmptyState>
              ) : (
                <ul className="space-y-1.5">
                  {bill.cosponsors.map((c) => (
                    <li key={c.bioguide_id} className="flex items-center justify-between gap-2">
                      <Link
                        href={`/members/${c.bioguide_id}`}
                        className={`text-sm hover:underline ${partyTextClass(c.party)}`}
                      >
                        {c.official_full_name ?? c.bioguide_id}
                      </Link>
                      {c.state && <span className="text-xs text-slate-400">{c.state}</span>}
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
