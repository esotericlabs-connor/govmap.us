import { MemberLink } from "@/components/MemberLink";
import type { CandidateMemberMatch } from "@/lib/api";

export function CandidateMemberLink({ match }: { match: CandidateMemberMatch | null | undefined }) {
  if (!match) return <span>Member-profile matching unavailable</span>;
  if (match.status === "ambiguous") return <span>Profile link withheld: conflicting ID matches</span>;
  if (match.status === "unmatched") return <span>No linked GovMap member profile</span>;
  if (!match.profile) return <span>Member-profile matching unavailable</span>;
  return (
    <MemberLink
      bioguide={match.profile.bioguide_id}
      className="font-semibold text-govblue-600 underline-offset-2 hover:underline"
    >
      {match.profile.in_office ? "GovMap profile" : "Former member profile"}
      {" · "}{match.profile.official_full_name}
    </MemberLink>
  );
}
