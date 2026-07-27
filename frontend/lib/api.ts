/**
 * API access + shared response types.
 *
 * Two base URLs by design: server components render inside the frontend
 * container and reach the backend directly over the compose network
 * (API_INTERNAL_URL); the browser calls the frontend's own origin with a
 * relative "/api/..." path, which a Next.js rewrite (next.config.mjs) proxies
 * to the backend server-side. That keeps client fetches same-origin so they
 * don't depend on the api.* host being reachable/unblocked from the device.
 */

export function serverApiBase(): string {
  return (
    process.env.API_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000"
  );
}

// Browser API calls are same-origin and relative ("/api/..."). A Next.js
// rewrite (see next.config.mjs) proxies them from the frontend origin to the
// backend server-side, so the client never depends on the api.* hostname being
// baked in, reachable, or CORS-allowed — which is exactly what broke on mobile
// (cross-origin request to api.govmap.us blocked/unreachable from the device).
export const publicApiBase = "";

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
  contributions: number | null;
  individual_contributions: number | null;
  individual_itemized: number | null;
  individual_unitemized: number | null;
  pac_contributions: number | null;
  party_contributions: number | null;
  transfers: number | null;
  candidate_contribution: number | null;
  other_receipts: number | null;
  loans: number | null;
  operating_expenditures: number | null;
  refunded_individual: number | null;
  coverage_start: string | null;
  coverage_end: string | null;
}

export interface Contribution {
  sub_id: string;
  contributor_name: string | null;
  employer: string | null;
  occupation: string | null;
  city: string | null;
  state: string | null;
  amount: number | null;
  date: string | null;
  aggregate_ytd: number | null;
}

export interface DonationsResponse {
  bioguide_id: string;
  cycle: number;
  committee_id: string | null;
  total: number | null;
  cached: number;
  complete: boolean;
  sort: string;
  q: string | null;
  offset: number;
  limit: number;
  items: Contribution[];
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
  summary: string | null;
  summary_date: string | null;
  text_url: string | null;
  text_version: string | null;
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

/** Full legislative text (plain, indentation preserved) from /api/bills/{id}/text.
 *  Fetched on demand from GPO/govinfo; `truncated` marks a very long bill cut to
 *  the storage cap. */
export interface BillText {
  bill_id: string;
  text_version: string | null;
  source_url: string | null;
  plain: string | null;
  truncated: boolean;
  fetched_at: string | null;
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

export interface CommitteeMeeting {
  event_id: string;
  title: string | null;
  meeting_type: string | null;
  status: string | null;
  datetime: string | null;
  location: string | null;
  bill_ids: string[];
}

export interface Subcommittee {
  committee_id: string;
  name: string;
}

export interface CommitteeDetail {
  committee_id: string;
  name: string;
  chamber: string;
  committee_type: string | null;
  parent_committee_id: string | null;
  url: string | null;
  members: CommitteeMemberRow[];
  subcommittees: Subcommittee[];
  upcoming_meetings: CommitteeMeeting[];
  recent_meetings: CommitteeMeeting[];
}

/** One bill referred to a committee, from /api/committees/{id}/bills (fetched on
 *  demand; title/latest_action filled from our corpus where we hold the bill). */
export interface CommitteeReferredBill {
  bill_id: string;
  bill_type: string;
  number: number | string | null;
  relationship: string | null;
  title: string | null;
  latest_action: string | null;
}

export interface CommitteeReferredBills {
  committee_id: string;
  bills: CommitteeReferredBill[];
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

/** Curated, sourced context for a vacant seat (see backend app/vacancies.py). */
export interface VacancyInfo {
  special_election_date?: string;
  note?: string;
  source_url?: string;
}

export interface CongressMap {
  house: Record<string, MapEntry>;
  senate: Record<string, MapEntry[]>;
  /** ISO timestamp the roster (congress-legislators) was last refreshed. */
  roster_updated?: string | null;
  /** STATE-DISTRICT -> curated special-election context for vacant seats. */
  vacancies?: Record<string, VacancyInfo>;
}

/** Compact member card for the map's info panel (/api/members/{id}/card):
 *  identity + tenure + a rolling activity pulse over `activity_window_days`. */
export interface MemberCard {
  bioguide_id: string;
  official_full_name: string;
  last_name: string;
  party: string;
  state: string;
  district: number | null;
  chamber: "house" | "senate";
  photo_url: string | null;
  served_since: string | null;
  leadership_role: string | null;
  recent_bills: number;
  recent_votes: number;
  activity_window_days: number;
}

/** Client-side fetch for the map info card. Fail-soft: returns null on any
 *  error so the panel can fall back to the name/party it already has. */
export async function fetchMemberCard(
  bioguide: string,
  days = 90,
): Promise<MemberCard | null> {
  try {
    const res = await fetch(`${publicApiBase}/api/members/${bioguide}/card?days=${days}`);
    if (!res.ok) return null;
    return (await res.json()) as MemberCard;
  } catch {
    return null;
  }
}

/** Client-side fetch of the full member profile, for the slide-in blade. Same
 *  shape the SSR profile page uses; fail-soft (null) so the blade can show a
 *  graceful error with a link out to the full page. */
export async function fetchMemberDetail(bioguide: string): Promise<MemberDetail | null> {
  try {
    const res = await fetch(`${publicApiBase}/api/members/${encodeURIComponent(bioguide)}`);
    if (!res.ok) return null;
    return (await res.json()) as MemberDetail;
  } catch {
    return null;
  }
}
