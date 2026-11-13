import { notFound } from "next/navigation";
import { Suspense } from "react";

import { BillProgress, OutcomePill } from "@/components/BillProgress";
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
import { MemberLink } from "@/components/MemberLink";
import { LocalList } from "@/components/LocalList";
import { PageSkeleton } from "@/components/PageSkeleton";
import { Reveal } from "@/components/Reveal";
import { apiGet, HttpError, type BillDetail, type BillText } from "@/lib/api";
import { billProgress, ordinal } from "@/lib/bill-progress.mjs";
import { externalHref } from "@/lib/safe-url.mjs";

export const dynamic = "force-dynamic";

async function getBill(billId: string): Promise<BillDetail | null> {
  try {
    return await apiGet<BillDetail>(`/api/bills/${encodeURIComponent(billId)}`);
  } catch (err) {
    if (err instanceof HttpError && err.status === 404) return null;
    throw err;
  }
}

async function getBillText(billId: string): Promise<BillText | null> {
  // Capacity or concurrent-refresh failures get an unavailable notice.
  try {
    return await apiGet<BillText>(`/api/bills/${encodeURIComponent(billId)}/text`);
  } catch (err) {
    if (err instanceof HttpError && err.status === 503) throw err;
    return null;
  }
}

function BillTextSkeleton() {
  return (
    <Section title="Full text">
      <div className="space-y-3">
        <div className="h-4 w-1/3 animate-pulse rounded bg-slate-warm-200" />
        <div className="h-72 w-full animate-pulse rounded-lg bg-slate-warm-100" />
      </div>
    </Section>
  );
}

// Streamed in its own Suspense boundary — the first request fetches the text
// from GPO/govinfo (a few seconds), so the rest of the page never waits on it.
async function BillFullText({ billId }: { billId: string }) {
  let text: BillText | null;
  try {
    text = await getBillText(billId);
  } catch (err) {
    if (!(err instanceof HttpError) || err.status !== 503) throw err;
    return (
      <Section title="Full text">
        <EmptyState>Full text is temporarily unavailable. Please try again later.</EmptyState>
      </Section>
    );
  }
  if (!text?.plain) return null;
  const sourceHref = externalHref(text.source_url);

  return (
    <Section title="Full text">
      <div className="space-y-4">
        <p className="text-xs text-slate-warm-400">
          {text.text_version ? `${text.text_version} · ` : ""}Official text via GPO
          {sourceHref && (
            <>
              {" · "}
              <a
                href={sourceHref}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-govblue transition-colors hover:text-govblue-600"
              >
                view source ↗
              </a>
            </>
          )}
        </p>
        <div className="max-h-[640px] overflow-auto rounded-lg border border-slate-warm-200 bg-slate-warm-50/70 p-5">
          <pre className="whitespace-pre-wrap break-words font-mono text-[13px] leading-relaxed text-slate-warm-700">
            {text.plain}
          </pre>
        </div>
        {text.truncated && (
          <p className="text-xs text-slate-warm-400">
            This is a very long bill — the text is truncated here; use “view source” for the
            complete document.
          </p>
        )}
      </div>
    </Section>
  );
}

export async function generateMetadata({ params }: { params: Promise<{ billId: string }> }) {
  const { billId } = await params;
  const bill = await getBill(billId).catch(() => null);
  const label = bill ? `${bill.bill_type.toUpperCase()} ${bill.number}` : "Bill";
  return { title: bill?.title ?? label };
}

async function BillDetailContent({ billId }: { billId: string }) {
  const bill = await getBill(billId);
  if (!bill) notFound();

  const label = `${bill.bill_type.toUpperCase()} ${bill.number}`;
  const textHref = externalHref(bill.text_url);
  const progress = billProgress(bill);

  return (
    <Reveal>
      <header className="mt-6">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <CodePill>{label}</CodePill>
          {bill.congress && (
            <p className="text-sm font-medium text-slate-warm-500">{ordinal(bill.congress)} Congress</p>
          )}
          <OutcomePill progress={progress} />
        </div>
        <h1 className="mt-3 font-display text-4xl font-bold tracking-tight text-govnavy sm:text-5xl">
          {bill.title ?? label}
        </h1>
        <div className="mt-6">
          <BillProgress progress={progress} />
        </div>
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
            {(bill.summary || textHref) && (
              <Section title="What this bill does (official CRS summary)">
                {bill.summary ? (
                  <p className="whitespace-pre-line leading-relaxed text-slate-warm-700">
                    {bill.summary}
                  </p>
                ) : (
                  <EmptyState>
                    The Congressional Research Service hasn&apos;t published a summary of this
                    bill yet.
                  </EmptyState>
                )}
                {textHref && (
                  <a
                    href={textHref}
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
                <LocalList
                  id="actions"
                  label="Actions"
                  groupLabel="chambers"
                  as="ol"
                  className="relative -ml-1 border-l-2 border-slate-warm-200"
                  items={bill.actions.map((a, i) => ({
                    id: a.seq,
                    name: a.text,
                    date: a.action_date,
                    group: a.chamber,
                    text: `${a.text} ${a.action_date ?? ""} ${a.chamber ?? ""}`,
                    content: (
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
                    ),
                  }))}
                />
              )}
            </Section>

            <Suspense fallback={<BillTextSkeleton />}>
              <BillFullText billId={billId} />
            </Suspense>
          </div>
        </div>

        {/* Sidebar: sponsor + cosponsors */}
        <aside className="space-y-10">
          {bill.sponsor && (
            <Section title="Sponsor">
              <MemberLink
                bioguide={bill.sponsor.bioguide_id}
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
              </MemberLink>
            </Section>
          )}

          <Section title="Cosponsors" count={bill.cosponsors.length}>
            {bill.cosponsors.length === 0 ? (
              <EmptyState>No cosponsors on this bill.</EmptyState>
            ) : (
              <LocalList
                id="cosponsors"
                label="Cosponsors"
                groupLabel="parties"
                as="ul"
                className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2 lg:grid-cols-1"
                items={bill.cosponsors.map((c) => ({
                  id: c.bioguide_id,
                  name: c.official_full_name,
                  date: c.sponsorship_date,
                  group: c.party,
                  text: `${c.official_full_name ?? ""} ${c.bioguide_id} ${c.party ?? ""} ${c.state ?? ""}`,
                  content: (
                  <li key={c.bioguide_id}>
                    <MemberLink
                      bioguide={c.bioguide_id}
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
                    </MemberLink>
                  </li>
                  ),
                }))}
              />
            )}
          </Section>
        </aside>
      </div>
    </Reveal>
  );
}

export default async function BillDetailPage({ params }: { params: Promise<{ billId: string }> }) {
  const { billId } = await params;
  return (
    <>
      <main className="bg-slate-warm-50 pb-20 pt-28">
        <div className="mx-auto max-w-6xl px-6">
          <BackLink href="/bills">All Bills</BackLink>
          <Suspense fallback={<PageSkeleton />}>
            <BillDetailContent billId={billId} />
          </Suspense>
        </div>
      </main>
    </>
  );
}
