import Link from "next/link";

import { MemberAvatar } from "@/components/MemberAvatar";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

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
  term_start: string;
  fec_candidate_ids: string[];
  photo_url: string | null;
};

async function getMembers(): Promise<Member[]> {
  // Runs server-side in the frontend container; reach the backend directly
  // over the compose network rather than through the public API hostname.
  const apiUrl =
    process.env.API_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000";
  const res = await fetch(`${apiUrl}/api/members?limit=600`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`failed to load members: ${res.status}`);
  }
  return res.json();
}

function partyColor(party: string): string {
  if (party.startsWith("Republican")) return "text-govred";
  if (party.startsWith("Democrat")) return "text-govblue";
  return "text-slate-500";
}

function seatLabel(member: Member): string {
  const where =
    member.district !== null ? `${member.state}-${member.district}` : member.state;
  const chamber = member.chamber === "senate" ? "Senate" : "House";
  return `${where} · ${chamber}`;
}

export default async function MembersPage() {
  let members: Member[] = [];
  let loadError = false;
  try {
    members = await getMembers();
  } catch (err) {
    console.error(err);
    loadError = true;
  }

  return (
    <>
      <SiteHeader variant="app" />
      <main className="min-h-screen bg-slate-50 pb-20 pt-24">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
          <Reveal>
            <div className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-card">
              <h1 className="font-display text-3xl font-bold tracking-tight text-govnavy">
                Members of Congress
              </h1>
              <p className="mt-1 text-slate-500">
                Browse all {members.length > 0 ? members.length : ""}{" "}
                currently-serving members of the U.S. House and Senate.
              </p>
            </div>

            {loadError ? (
              <div className="mt-8 rounded-xl border border-red-200/80 bg-red-50/80 p-6 text-center">
                <h2 className="font-semibold text-red-800">Could not load members</h2>
                <p className="mt-1 text-sm text-red-700">
                  There was an issue fetching data from the backend. Please try again in a moment.
                </p>
              </div>
            ) : (
              <div className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {members.map((member) => (
                  <Link
                    key={member.bioguide_id}
                    href={`/members/${member.bioguide_id}`}
                    className="group block rounded-lg border border-slate-200/80 bg-white p-4 shadow-sm transition-all duration-150 ease-in-out hover:scale-[1.02] hover:border-slate-300 hover:shadow-md"
                  >
                    <div className="flex items-center gap-4">
                      <MemberAvatar
                        src={member.photo_url}
                        name={member.official_full_name}
                        size="md"
                      />
                      <div className="min-w-0">
                        <p className="truncate font-bold text-govnavy group-hover:text-govblue">
                          {member.official_full_name}
                        </p>
                        <p className="text-sm text-slate-500">
                          <span className={`font-semibold ${partyColor(member.party)}`}>
                            {member.party}
                          </span>{" "}
                          · {seatLabel(member)}
                        </p>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </Reveal>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
