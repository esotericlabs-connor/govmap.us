import type { CandidateMemberMatch } from "@/lib/api";

export type CampaignMoneyCandidate = {
  finance_cycle: number;
  candidate_id: string;
  name: string | null;
  office: "H" | "S" | "P";
  state: string | null;
  district: string | null;
  party: string | null;
  incumbent_challenge: string | null;
  receipts: string | null;
  transfers_from_authorized: string | null;
  disbursements: string | null;
  transfers_to_authorized: string | null;
  cash_beginning: string | null;
  cash_on_hand: string | null;
  candidate_contributions: string | null;
  candidate_loans: string | null;
  other_loans: string | null;
  candidate_loan_repayments: string | null;
  other_loan_repayments: string | null;
  debts: string | null;
  individual_contributions: string | null;
  other_committee_contributions: string | null;
  party_contributions: string | null;
  individual_refunds: string | null;
  committee_refunds: string | null;
  coverage_end: string | null;
  member_match?: CandidateMemberMatch | null;
};

export type CampaignMoneyCoverage = {
  finance_cycle: number;
  candidate_count: number;
  linkage_count: number;
  summary_sha256: string;
  summary_last_modified: string | null;
  linkage_sha256: string;
  linkage_last_modified: string | null;
  snapshot_revision: string;
  fetched_at: string;
};

export type CampaignMoneyList = {
  generated_at: string;
  finance_cycle: number;
  available: boolean;
  coverage: CampaignMoneyCoverage | null;
  matching_count: number;
  filtered_count: number;
  reporting_dates: { coverage_end: string; candidate_count: number }[];
  reporting_dates_truncated: boolean;
  selected_date: string | null;
  limit: number;
  offset: number;
  candidates: CampaignMoneyCandidate[];
};

export type CampaignMoneyDetail = {
  generated_at: string;
  coverage: CampaignMoneyCoverage;
  candidate: CampaignMoneyCandidate;
  catalog_match: {
    candidate_status: string | null;
    election_years: number[];
    state: string | null;
    district: string | null;
  } | null;
  related_candidates?: {
    candidates: { candidate_id: string; finance_cycles: number[] }[];
    withheld_count: number;
  } | null;
  linkage_count: number;
  filtered_linkage_count: number;
  limit: number;
  offset: number;
  linkages: {
    subject_id: string;
    candidate_election_year: number;
    candidate_election_year_outside_supported_range: boolean;
    fec_election_year: number;
    committee_id: string | null;
    committee_type: string | null;
    designation: string | null;
    linkage_id: number;
  }[];
};
