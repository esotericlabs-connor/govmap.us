// Always rendered on demand, never pre-rendered at build time. The backend
// isn't reachable during the Docker image build, so pre-rendering would try
// to fetch from a dead host and fail the build; this opts the route out of
// static generation entirely.
export const dynamic = "force-dynamic";

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
  // This runs server-side (in the frontend container), so prefer the internal
  // service URL and reach the backend directly over the compose network rather
  // than hairpinning out through the public api.govmap.us hostname.
  const apiUrl =
    process.env.API_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000";
  const res = await fetch(`${apiUrl}/api/members?limit=535`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`failed to load members: ${res.status}`);
  }
  return res.json();
}

export default async function MembersPage() {
  let members: Member[] = [];
  let loadError = false;
  try {
    members = await getMembers();
  } catch {
    loadError = true;
  }

  if (loadError) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <h1 className="mb-2 text-2xl font-bold">Members of Congress</h1>
        <p className="text-slate-500">
          Couldn&apos;t load members right now. Please try again shortly.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <h1 className="mb-6 text-2xl font-bold">
        Members of Congress ({members.length})
      </h1>
      <ul className="divide-y divide-slate-200">
        {members.map((member) => (
          <li
            key={member.bioguide_id}
            className="flex items-center justify-between py-3"
          >
            <div>
              <p className="font-medium">{member.official_full_name}</p>
              <p className="text-sm text-slate-500">
                {member.party} — {member.state}
                {member.district !== null ? `-${member.district}` : ""} (
                {member.chamber === "senate" ? "Senate" : "House"})
              </p>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
