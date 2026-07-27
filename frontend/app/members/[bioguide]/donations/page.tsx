import { notFound } from "next/navigation";
import { Suspense } from "react";

import {
  BackLink,
  chamberLabel,
  partyDotClass,
  partyTextClass,
} from "@/components/DetailKit";
import { DonationsLedger } from "@/components/DonationsLedger";
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
        <DonationsLedger
          bioguide={bioguide}
          cycle={data.cycle}
          initial={data}
          initSort={sort}
          initQ={q}
          initOffset={offset}
        />
      </div>
    </Reveal>
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
          <Suspense fallback={<PageSkeleton />}>
            <DonationsContent bioguide={params.bioguide} offset={offset} sort={sort} q={q} />
          </Suspense>
        </div>
      </main>
    </>
  );
}
