import Link from "next/link";
import { notFound } from "next/navigation";
import { type ReactNode, Suspense } from "react";

import {
  BackLink,
  chamberLabel,
  EmptyState,
  formatDate,
  partyDotClass,
  partyTextClass,
  Section,
} from "@/components/DetailKit";
import { DonationControls } from "@/components/DonationControls";
import { MemberAvatar } from "@/components/MemberAvatar";
import { PageSkeleton } from "@/components/PageSkeleton";
import { Reveal } from "@/components/Reveal";
import { SiteHeader } from "@/components/SiteHeader";
import {
  apiGet,
  type DonationsResponse,
  HttpError,
  type MemberDetail,
} from "@/lib/api";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 50;

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function money(n: number | null): string {
  return n === null || Number.isNaN(n) ? "—" : USD.format(n);
}

function toTitle(s: string | null): string | null {
  if (!s) return null;
  // FEC stores names/employers in ALL CAPS; soften to Title Case for reading.
  return s
    .toLowerCase()
    .replace(/\b([a-z])/g, (m) => m.toUpperCase())
    .replace(/\b(Llc|Llp|Pac|Ii|Iii|Iv)\b/g, (m) => m.toUpperCase());
}

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
  return { title: member ? `${member.official_full_name} — Donations` : "Donations" };
}

async function DonationsContent({
  bioguide,
  offset,
  sort,
  q,
}: {
  bioguide: string;
  offset: number;
  sort: string;
  q: string;
}) {
  const query = new URLSearchParams({ offset: String(offset), limit: String(PAGE_SIZE), sort });
  if (q) query.set("q", q);
  const [member, data] = await Promise.all([
    getMember(bioguide),
    apiGet<DonationsResponse>(
      `/api/members/${encodeURIComponent(bioguide)}/donations?${query.toString()}`,
    ),
  ]);
  if (!member) notFound();

  const items = data.items;
  const total = data.total;
  const shownFrom = items.length ? offset + 1 : 0;
  const shownTo = offset + items.length;
  const hasPrev = offset > 0;
  const hasNext = total !== null ? offset + PAGE_SIZE < total : items.length === PAGE_SIZE;
  const base = `/members/${bioguide}/donations`;
  // Preserve the active sort + search when paging (offset-only links would
  // silently reset them to the default largest-first view).
  const pageHref = (o: number) => {
    const p = new URLSearchParams({ offset: String(Math.max(0, o)) });
    if (sort && sort !== "amount") p.set("sort", sort);
    if (q) p.set("q", q);
    return `${base}?${p.toString()}`;
  };

  return (
    <Reveal>
      <header className="mt-6">
        <div className="flex items-center gap-4">
          <MemberAvatar src={member.photo_url} name={member.official_full_name} size="xl" />
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <span className={`h-2 w-2 rounded-full ${partyDotClass(member.party)}`} />
              <span className={partyTextClass(member.party)}>{member.party}</span>
              <span className="text-slate-warm-400">
                · {member.district !== null ? `${member.state}-${member.district}` : member.state}{" "}
                · {chamberLabel(member.chamber)}
              </span>
            </div>
            <h1 className="mt-1 font-display text-3xl font-bold tracking-tight text-govnavy sm:text-4xl">
              {member.official_full_name}
            </h1>
            <p className="mt-1 text-lg text-slate-warm-500">
              Itemized campaign donations · {data.cycle} cycle
            </p>
          </div>
        </div>
      </header>

      <div className="mt-10">
        <Section title="Contributions" count={total ?? undefined}>
          <DonationControls sort={data.sort} q={data.q ?? ""} />
          {items.length === 0 ? (
            <EmptyState>
              {data.q
                ? `No contributions match “${data.q}”.`
                : `No itemized contributions found for this member in the ${data.cycle} cycle.`}
            </EmptyState>
          ) : (
            <>
              <ul className="-my-1 divide-y divide-slate-warm-100">
                {items.map((c) => {
                  const name = toTitle(c.contributor_name) ?? "—";
                  const place = [c.city ? toTitle(c.city) : null, c.state]
                    .filter(Boolean)
                    .join(", ");
                  const work = [toTitle(c.occupation), toTitle(c.employer)]
                    .filter(Boolean)
                    .join(" · ");
                  return (
                    <li
                      key={c.sub_id}
                      className="flex items-start justify-between gap-4 py-3.5"
                    >
                      <div className="min-w-0">
                        <p className="font-semibold text-slate-800">{name}</p>
                        <p className="mt-0.5 text-sm text-slate-warm-500">
                          {place}
                          {place && work && " — "}
                          {work}
                        </p>
                      </div>
                      <div className="flex-shrink-0 text-right">
                        <p className="font-display text-lg font-bold text-govnavy">
                          {money(c.amount)}
                        </p>
                        {c.date && (
                          <p className="mt-0.5 text-sm text-slate-warm-400">{formatDate(c.date)}</p>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>

              <div className="mt-8 flex items-center justify-between border-t border-slate-warm-200 pt-6">
                <p className="text-sm text-slate-warm-500">
                  {total !== null ? (
                    <>
                      Showing <strong>{shownFrom.toLocaleString()}</strong>–
                      <strong>{shownTo.toLocaleString()}</strong> of{" "}
                      <strong>{total.toLocaleString()}</strong>
                    </>
                  ) : (
                    <>
                      Showing {shownFrom.toLocaleString()}–{shownTo.toLocaleString()}
                    </>
                  )}
                </p>
                <div className="flex gap-2">
                  <PageLink href={pageHref(offset - PAGE_SIZE)} disabled={!hasPrev}>
                    ← Prev
                  </PageLink>
                  <PageLink href={pageHref(offset + PAGE_SIZE)} disabled={!hasNext}>
                    Next →
                  </PageLink>
                </div>
              </div>
            </>
          )}

          <p className="mt-8 border-t border-slate-warm-200 pt-6 text-xs leading-relaxed text-slate-warm-400">
            Every disclosed contribution of <strong>$200 or more</strong> to this member&rsquo;s
            principal campaign committee. Small-dollar gifts under $200 aren&rsquo;t itemized by the
            FEC and so don&rsquo;t appear individually. Search and the alternate sorts cover the
            contributions loaded so far — browse the default largest-first view to load more. Records
            are pulled and cached on demand from the FEC. Source: Federal Election Commission.
          </p>
        </Section>
      </div>
    </Reveal>
  );
}

function PageLink({
  href,
  disabled,
  children,
}: {
  href: string;
  disabled: boolean;
  children: ReactNode;
}) {
  if (disabled) {
    return (
      <span className="cursor-not-allowed rounded-full border border-slate-warm-200 px-4 py-2 text-sm font-semibold text-slate-warm-300">
        {children}
      </span>
    );
  }
  return (
    <Link
      href={href}
      className="rounded-full border border-slate-warm-200 px-4 py-2 text-sm font-semibold text-slate-warm-700 transition-colors hover:border-govnavy hover:text-govnavy"
    >
      {children}
    </Link>
  );
}

export default function DonationsPage({
  params,
  searchParams,
}: {
  params: { bioguide: string };
  searchParams: { offset?: string; sort?: string; q?: string };
}) {
  const parsed = Number.parseInt(searchParams.offset ?? "0", 10);
  const offset = Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  const sort = searchParams.sort ?? "amount";
  const q = searchParams.q ?? "";

  return (
    <>
      <SiteHeader variant="app" />
      <main className="bg-slate-warm-50 pb-20 pt-28">
        <div className="mx-auto max-w-4xl px-6">
          <BackLink href={`/members/${params.bioguide}`}>Back to member</BackLink>
          <Suspense key={`${offset}-${sort}-${q}`} fallback={<PageSkeleton />}>
            <DonationsContent bioguide={params.bioguide} offset={offset} sort={sort} q={q} />
          </Suspense>
        </div>
      </main>
    </>
  );
}
