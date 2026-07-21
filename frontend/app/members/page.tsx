import Image from "next/image";
import Link from "next/link";

// Rendered on demand, never prerendered — the backend isn't reachable during
// the Docker image build, so prerendering would fetch a dead host and fail
// the build.
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

function Header() {
  return (
    <header className="flex items-center justify-between gap-4 bg-govnavy px-6 py-3">
      <Link href="/" className="shrink-0">
        <Image src="/logo-dark.png" alt="GovMap.us" width={140} height={79} priority />
      </Link>
      <Link href="/" className="text-sm font-medium text-white/70 transition-colors hover:text-white">
        ← Home
      </Link>
    </header>
  );
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
    <div className="min-h-screen bg-white">
      <Header />
      <main className="mx-auto max-w-4xl px-6 py-12">
        {loadError ? (
          <>
            <h1 className="mb-2 text-2xl font-bold">Members of Congress</h1>
            <p className="text-slate-500">
              Couldn&apos;t load members right now. Please try again shortly.
            </p>
          </>
        ) : (
          <>
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
          </>
        )}
      </main>
    </div>
  );
}
