import { MemberAvatar } from "@/components/MemberAvatar";
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
  } catch {
    loadError = true;
  }

  return (
    <>
      <SiteHeader variant="app" />
      <main className="min-h-screen bg-white pb-16 pt-24">
        <div className="mx-auto max-w-4xl px-6 py-10">
          {loadError ? (
            <>
              <h1 className="mb-2 font-display text-3xl font-bold text-govnavy">
                Members of Congress
              </h1>
              <p className="text-slate-500">
                Couldn&apos;t load members right now. Please try again shortly.
              </p>
            </>
          ) : (
            <>
              <h1 className="mb-6 font-display text-3xl font-bold text-govnavy">
                Members of Congress{" "}
                <span className="font-normal text-slate-400">({members.length})</span>
              </h1>
              <ul className="divide-y divide-slate-100">
                {members.map((member) => (
                  <li key={member.bioguide_id} className="flex items-center gap-4 py-3">
                    <MemberAvatar src={member.photo_url} name={member.official_full_name} />
                    <div className="min-w-0">
                      <p className="truncate font-medium text-slate-900">
                        {member.official_full_name}
                      </p>
                      <p className="text-sm text-slate-500">
                        <span className={`font-medium ${partyColor(member.party)}`}>
                          {member.party}
                        </span>{" "}
                        · {seatLabel(member)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
