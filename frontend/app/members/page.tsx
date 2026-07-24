import { ChamberTabs } from "@/components/ChamberTabs";
import { MemberAvatar } from "@/components/MemberAvatar";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { apiGet } from "@/lib/api";
import Link from "next/link";
import { Suspense } from "react";

// Rendered on demand, never prerendered — the backend isn't reachable during
// the Docker image build, so prerendering would fetch a dead host and fail
// the build.
export const dynamic = "force-dynamic";

export const metadata = {
  title: "Members of Congress",
};

type Member = {
  bioguide_id: string;
  first_name: string;
  last_name: string;
  official_full_name: string;
  chamber: "house" | "senate";
  state: string;
  district: number | null;
  party: string;
  photo_url: string | null;
};

type Chamber = "house" | "senate";

async function getMembers(chamber: Chamber | null): Promise<Member[]> {
  const query = chamber ? `&chamber=${chamber}` : "";
  return await apiGet<Member[]>(`/api/members?limit=600${query}`);
}

function seatLabel(member: Member): string {
  const where =
    member.district !== null ? `${member.state}-${member.district}` : member.state;
  return `${where} · ${member.chamber === "senate" ? "Senate" : "House"}`;
}

async function MemberGrid({ chamber }: { chamber: Chamber | null }) {
  let members: Member[] = [];
  let loadError = false;
  try {
    members = await getMembers(chamber);
  } catch (err) {
    console.error(err);
    loadError = true;
  }

  if (loadError) {
    return (
      <div className="mt-10 rounded-2xl border border-red-200/80 bg-red-100/50 p-8 text-center">
        <h2 className="font-semibold text-red-900">Could not load members</h2>
        <p className="mt-2 text-red-800">
          There was an issue fetching data from the backend. Please try again in a moment.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {members.map((member, i) => (
        <Reveal key={member.bioguide_id} delay={i * 20}>
          <Link
            href={`/members/${member.bioguide_id}`}
            className="group block rounded-xl border border-slate-warm-200 bg-white p-4 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-card-hover"
          >
            <div className="flex items-center gap-4">
              <MemberAvatar src={member.photo_url} name={member.official_full_name} size="md" />
              <div className="min-w-0">
                <p className="truncate font-bold text-govnavy transition-colors group-hover:text-govblue-600">
                  {member.official_full_name}
                </p>
                <p className="flex items-center gap-1.5 text-sm text-slate-warm-500">
                  <span
                    className={`font-semibold ${
                      member.party.startsWith("R")
                        ? "text-govred"
                        : member.party.startsWith("D")
                          ? "text-govblue"
                          : ""
                    }`}
                  >
                    {member.party.slice(0, 1)}
                  </span>
                  <span>· {seatLabel(member)}</span>
                </p>
              </div>
            </div>
          </Link>
        </Reveal>
      ))}
    </div>
  );
}

function MemberGridSkeleton() {
  return (
    <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 12 }).map((_, i) => (
        <div key={i} className="h-20 w-full animate-pulse rounded-xl bg-slate-warm-200" />
      ))}
    </div>
  );
}

export default function MembersPage({
  searchParams,
}: {
  searchParams: { chamber?: string };
}) {
  const chamber: Chamber | null =
    searchParams.chamber === "house" || searchParams.chamber === "senate"
      ? searchParams.chamber
      : null;

  const scopeLabel =
    chamber === "house"
      ? "the U.S. House"
      : chamber === "senate"
        ? "the U.S. Senate"
        : "Congress";

  return (
    <>
      <SiteHeader variant="app" />
      <main className="bg-slate-warm-50 pb-20 pt-28">
        <div className="mx-auto max-w-7xl px-6">
          <Reveal>
            <div className="md:flex md:items-center md:justify-between">
              <div>
                <h1 className="font-display text-4xl font-bold tracking-tight text-govnavy sm:text-5xl">
                  Members of {scopeLabel}
                </h1>
                <p className="mt-2 text-lg text-slate-warm-600">
                  Browse all currently-serving members.
                </p>
              </div>
              <div className="mt-6 md:mt-0">
                <ChamberTabs />
              </div>
            </div>
          </Reveal>
          <Suspense fallback={<MemberGridSkeleton />}>
            <MemberGrid chamber={chamber} />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
