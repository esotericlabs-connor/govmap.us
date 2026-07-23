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
  Section,
} from "@/components/DetailKit";
import { MemberAvatar } from "@/components/MemberAvatar";
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

export default async function BillDetailPage({ params }: { params: { billId: string } }) {
  const bill = await getBill(params.billId);
  if (!bill) notFound();

  const label = `${bill.bill_type.toUpperCase()} ${bill.number}`;

  return (
    <>
      <SiteHeader variant="app" />
      <main className="min-h-screen bg-slate-50 pb-20 pt-24">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
          <BackLink href="/members">All Members</BackLink>

          <Reveal>
            <header className="mt-4 rounded-xl border border-slate-200/80 bg-white p-6 shadow-card">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <CodePill>{label}</CodePill>
                {bill.congress && (
                  <p className="text-sm text-slate-500">{bill.congress}th Congress</p>
                )}
                {bill.status && (
                  <p className="rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-bold text-green-800 ring-1 ring-inset ring-green-500/50">
                    {bill.status}
                  </p>
                )}
              </div>
              <h1 className="mt-3 font-display text-3xl font-bold tracking-tight text-govnavy">
                {bill.title ?? label}
              </h1>
              {bill.latest_action && (
                <div className="mt-4 rounded-lg border border-slate-200/80 bg-slate-50/80 p-4 text-sm">
                  <p className="font-semibold text-slate-600">
                    Latest action ({formatDate(bill.latest_action_date)})
                  </p>
                  <p className="mt-1 text-slate-800">{bill.latest_action}</p>
                </div>
              )}
            </header>

            <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-3">
              {/* Main content: timeline */}
              <div className="lg:col-span-2">
                <Section title="Action Timeline" count={bill.actions.length}>
                  {bill.actions.length === 0 ? (
                    <EmptyState>No actions found for this bill.</EmptyState>
                  ) : (
                    <ol className="relative border-l border-slate-200">
                      {bill.actions.map((a) => (
                        <li key={a.seq} className="mb-6 ml-6">
                          <span className="absolute -left-[9px] flex h-[18px] w-[18px] items-center justify-center rounded-full bg-slate-200 ring-8 ring-white">
                            <svg
                              className="h-4 w-4 text-white"
                              viewBox="0 0 24 24"
                              fill="currentColor"
                            >
                              <path d="M12,18A6,6 0 0,1 6,12C6,11 6.25,10.03 6.7,9.15L5.24,7.68C4.46,8.87 4,10.36 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12C20,10.36 19.54,8.87 18.76,7.68L17.3,9.15C17.75,10.03 18,11 18,12A6,6 0 0,1 12,18M12,4A8,8 0 0,0 4,12C4,12.79 4.14,13.55 4.38,14.25L5.84,12.79C5.8,12.54 5.75,12.27 5.75,12A6.25,6.25 0 0,1 12,5.75A6.25,6.25 0 0,1 18.25,12C18.25,12.27 18.2,12.54 18.16,12.79L19.62,14.25C19.86,13.55 20,12.79 20,12A8,8 0 0,0 12,4Z" />
                            </svg>
                          </span>
                          <div className="rounded-lg border border-slate-200/80 bg-white p-4">
                            <p className="text-sm font-medium text-slate-600">
                              {a.action_date ? formatDate(a.action_date) : "Date not specified"}
                              {a.chamber && ` · ${chamberLabel(a.chamber)}`}
                            </p>
                            <p className="mt-1 text-sm text-slate-800">{a.text}</p>
                          </div>
                        </li>
                      ))}
                    </ol>
                  )}
                </Section>
              </div>

              {/* Sidebar: sponsor + cosponsors */}
              <aside className="space-y-8">
                {bill.sponsor && (
                  <Section title="Sponsor">
                    <Link
                      href={`/members/${bill.sponsor.bioguide_id}`}
                      className="group -m-2 block rounded-lg p-2"
                    >
                      <div className="flex items-center gap-4">
                        <MemberAvatar
                          src={bill.sponsor.photo_url}
                          name={bill.sponsor.official_full_name ?? ""}
                          size="md"
                        />
                        <div className="min-w-0">
                          <p className="font-semibold text-govnavy group-hover:text-govblue">
                            {bill.sponsor.official_full_name}
                          </p>
                          <p className="flex items-center gap-1.5 text-sm text-slate-500">
                            <span
                              className={`h-2 w-2 rounded-full ${partyDotClass(
                                bill.sponsor.party,
                              )}`}
                            />
                            <span className={partyTextClass(bill.sponsor.party)}>
                              {bill.sponsor.party}
                            </span>
                            <span>· {bill.sponsor.state}</span>
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
                    <ul className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3 lg:grid-cols-2">
                      {bill.cosponsors.map((c) => (
                        <li key={c.bioguide_id}>
                          <Link
                            href={`/members/${c.bioguide_id}`}
                            className="inline-flex items-baseline gap-1.5 text-sm group"
                          >
                            <span
                              className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${partyDotClass(
                                c.party,
                              )}`}
                            />
                            <span className="font-medium text-slate-700 group-hover:text-govblue">
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
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
