/**
 * API access + shared response types.
 *
 * Two base URLs by design (see docker-compose): server components render inside
 * the frontend container and reach the backend directly over the compose
 * network (API_INTERNAL_URL); the browser uses the public API host baked in at
 * build time (NEXT_PUBLIC_API_URL).
 */

export function serverApiBase(): string {
  return (
    process.env.API_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000"
  );
}

// Inlined into the client bundle at build time by Next (NEXT_PUBLIC_*).
export const publicApiBase =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class HttpError extends Error {
  constructor(public status: number) {
    super(`request failed: ${status}`);
  }
}

/** Server-side JSON GET used by SSR pages. Uncached — data refreshes every
 *  30 min and freshness beats shaving a few ms. Throws HttpError on non-2xx so
 *  pages can map 404 -> notFound(). */
export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${serverApiBase()}${path}`, { cache: "no-store" });
  if (!res.ok) throw new HttpError(res.status);
  return (await res.json()) as T;
}

// --- Response shapes (mirror the FastAPI routers) ---

export interface MemberSummary {
  bioguide_id: string;
  official_full_name: string;
  party: string;
  state: string;
  chamber: "house" | "senate";
  photo_url: string | null;
}

export interface CommitteeSeat {
  committee_id: string;
  name: string;
  parent_committee_id: string | null;
  role: string | null;
  side: string | null;
}

export interface SponsoredBill {
  bill_id: string;
  bill_type: string;
  number: number;
  title: string | null;
  introduced_date: string | null;
  latest_action: string | null;
}

export interface VotingRecordEntry {
  vote_id: string;
  chamber: string;
  date: string | null;
  question: string | null;
  result: string | null;
  bill_id: string | null;
  position: string | null;
}

export interface MemberFinance {
  cycle: number;
  fec_candidate_id: string;
  receipts: number | null;
  disbursements: number | null;
  cash_on_hand: number | null;
  debts: number | null;
  individual_contributions: number | null;
  pac_contributions: number | null;
  party_contributions: number | null;
  coverage_start: string | null;
  coverage_end: string | null;
}

export interface MemberDetail {
  bioguide_id: string;
  first_name: string;
  last_name: string;
  official_full_name: string;
  chamber: "house" | "senate";
  state: string;
  district: number | null;
  party: string;
  term_start: string | null;
  served_since: string | null;
  photo_url: string | null;
  birthday: string | null;
  gender: string | null;
  contact: Record<string, string> | null;
  leadership_role: string | null;
  finance: MemberFinance | null;
  ids: {
    fec: string[];
    govtrack: number | null;
    opensecrets: string | null;
    thomas: string | null;
    lis: string | null;
  };
  committees: CommitteeSeat[];
  sponsored_bills_total: number;
  sponsored_bills: SponsoredBill[];
  voting_record: VotingRecordEntry[];
}

export interface BillAction {
  seq: number;
  action_date: string | null;
  chamber: string | null;
  text: string;
  action_type: string | null;
}

export interface BillCosponsor {
  bioguide_id: string;
  official_full_name: string | null;
  party: string | null;
  state: string | null;
  sponsorship_date: string | null;
  is_original: boolean | null;
}

export interface BillDetail {
  bill_id: string;
  congress: number;
  bill_type: string;
  number: number;
  title: string | null;
  introduced_date: string | null;
  latest_action: string | null;
  latest_action_date: string | null;
  status: string | null;
  policy_area: string | null;
  update_date: string | null;
  sponsor: {
    bioguide_id: string;
    official_full_name: string | null;
    party: string | null;
    state: string | null;
    photo_url: string | null;
  } | null;
  actions: BillAction[];
  cosponsors: BillCosponsor[];
}

export interface VotePosition {
  bioguide_id: string;
  official_full_name: string | null;
  party: string | null;
  state: string | null;
  position: string | null;
}

export interface VoteDetail {
  vote_id: string;
  chamber: string;
  congress: number;
  session: number;
  roll_number: number;
  date: string | null;
  question: string | null;
  result: string | null;
  bill_id: string | null;
  totals: Record<string, number | null> | null;
  source_url: string | null;
  positions: VotePosition[];
}

export interface CommitteeMemberRow {
  bioguide_id: string;
  official_full_name: string;
  party: string;
  state: string;
  photo_url: string | null;
  role: string | null;
  side: string | null;
  rank: number | null;
}

// Alias used by the committee detail page.
export type CommitteeMember = CommitteeMemberRow;

export interface CommitteeDetail {
  committee_id: string;
  name: string;
  chamber: string;
  committee_type: string | null;
  parent_committee_id: string | null;
  url: string | null;
  members: CommitteeMemberRow[];
}

export interface SearchResults {
  query: string;
  members: MemberSummary[];
  bills: { bill_id: string; bill_type: string; number: number; title: string | null; latest_action: string | null }[];
  votes: { vote_id: string; chamber: string; date: string | null; question: string | null; result: string | null }[];
  committees: { committee_id: string; name: string; chamber: string }[];
}

// --- Congress dashboard / map (/congress) ---

/** Fuller member shape returned by /api/lookup and reused for reps cards. */
export interface LookupMember {
  bioguide_id: string;
  official_full_name: string;
  last_name: string;
  party: string;
  state: string;
  district: number | null;
  chamber: "house" | "senate";
  photo_url: string | null;
}

export interface LookupResult {
  zip: string;
  districts: { state: string; district: number }[];
  senators: LookupMember[];
  representatives: LookupMember[];
}

export interface ChamberBalance {
  D: number;
  R: number;
  I: number;
  total: number;
}

export interface ChamberSummary {
  house: ChamberBalance;
  senate: ChamberBalance;
}

/** Party/link index from /api/map. House keyed `STATE-DISTRICT` (district 0 =
 *  at-large); Senate keyed by state (its two seats). */
export interface MapEntry {
  bioguide: string;
  last_name: string;
  party: string;
}

export interface CongressMap {
  house: Record<string, MapEntry>;
  senate: Record<string, MapEntry[]>;
}
