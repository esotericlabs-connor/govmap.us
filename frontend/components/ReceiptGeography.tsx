"use client";

import { useState } from "react";

import { formatMoneyExact, maxPositiveMoney, moneyPercent } from "@/lib/money.mjs";

type ReceiptState = {
  state: string | null;
  state_full: string | null;
  receipt_count: number;
  amount: string;
};

type ReceiptGeographyData = {
  candidate_id: string;
  finance_cycle: number;
  fetched_at: string;
  state_group_count: number;
  source_count_exact: boolean | null;
  states: ReceiptState[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isReceiptGeographyData(value: unknown): value is ReceiptGeographyData {
  if (!isRecord(value) || !Array.isArray(value.states)) return false;
  if (
    typeof value.candidate_id !== "string"
    || !/^[HSP][A-Z0-9]{8}$/.test(value.candidate_id)
    || typeof value.finance_cycle !== "number"
    || !Number.isSafeInteger(value.finance_cycle)
    || typeof value.fetched_at !== "string"
    || !Number.isFinite(Date.parse(value.fetched_at))
    || typeof value.state_group_count !== "number"
    || !Number.isSafeInteger(value.state_group_count)
    || (value.source_count_exact !== null && typeof value.source_count_exact !== "boolean")
  ) return false;
  return value.states.every((item: unknown) =>
    isRecord(item)
    && (item.state === null || (typeof item.state === "string" && /^[A-Z]{2}$/.test(item.state)))
    && (item.state_full === null || typeof item.state_full === "string")
    && typeof item.receipt_count === "number"
    && Number.isSafeInteger(item.receipt_count)
    && typeof item.amount === "string"
    && /^-?\d+(?:\.\d{1,2})?$/.test(item.amount),
  );
}

export function ReceiptGeography({
  candidateId,
  financeCycle,
}: {
  candidateId: string;
  financeCycle: number;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [data, setData] = useState<ReceiptGeographyData | null>(null);

  async function loadGeography() {
    setLoading(true);
    setError(false);
    try {
      const query = new URLSearchParams({ cycle: String(financeCycle) });
      const response = await fetch(
        `/api/money/candidates/${encodeURIComponent(candidateId)}/receipt-geography?${query}`,
        { cache: "no-store" },
      );
      if (!response.ok) throw new Error(`FEC aggregate request returned ${response.status}`);
      const payload: unknown = await response.json();
      if (!isReceiptGeographyData(payload)
        || payload.candidate_id !== candidateId
        || payload.finance_cycle !== financeCycle
        || payload.states.length !== payload.state_group_count) {
        throw new Error("FEC aggregate response failed validation");
      }
      setData(payload);
    } catch (requestError) {
      console.error("Candidate receipt geography could not be loaded", requestError);
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  const maximum = data ? maxPositiveMoney(data.states.map((item) => item.amount)) : null;

  return (
    <div className="space-y-4">
      {!data && (
        <>
          <p className="text-sm leading-6 text-ink-soft">
            Load FEC aggregates on demand. This makes one FEC request; no receipt-level donor
            identities are retrieved or displayed.
          </p>
          <button
            className="rounded-lg border border-line bg-surface px-4 py-2 text-sm font-semibold text-ink hover:bg-sunken disabled:cursor-wait disabled:opacity-60"
            disabled={loading}
            onClick={loadGeography}
            type="button"
          >
            {loading ? "Loading reported states..." : "Load itemized receipt geography"}
          </button>
        </>
      )}
      {error && (
        <p className="text-sm text-govred" role="alert">
          The FEC aggregate could not be loaded. The source may be unavailable, or its API budget may be exhausted.
        </p>
      )}
      {data && (
        <>
          <p className="text-sm leading-6 text-ink-soft">
            Reported contributor state for itemized Schedule A receipts only. Counts are FEC source
            records, not unique contributors; state does not establish residence or district.
            Unitemized amounts are excluded. Reported state groups:{" "}
            {data.state_group_count.toLocaleString()}
            {data.source_count_exact === false ? " (source count is approximate)" : ""}.
          </p>
          {data.states.length === 0 ? (
            <p className="text-sm text-ink-soft">The FEC returned no reported state groups for this cycle.</p>
          ) : (
            <>
              {maximum !== null && (
                <div aria-hidden="true" className="space-y-3">
                  {data.states.map((item) => (
                    <div key={item.state ?? "unreported"}>
                      <div className="flex flex-wrap justify-between gap-x-4 text-sm">
                        <span className="font-medium text-ink">
                          {item.state_full ?? item.state ?? "State not reported"}
                        </span>
                        <span className="tabular-nums text-ink-soft">{formatMoneyExact(item.amount)}</span>
                      </div>
                      <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-sunken">
                        <div
                          className="h-full rounded-full bg-emerald-600"
                          style={{ width: `${moneyPercent(item.amount, maximum)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className="overflow-x-auto rounded-lg border border-line">
                <table className="w-full text-left text-sm">
                  <thead className="bg-sunken text-xs uppercase tracking-wide text-ink-muted">
                    <tr>
                      <th className="px-3 py-2 font-semibold">Reported state</th>
                      <th className="px-3 py-2 text-right font-semibold">Source records</th>
                      <th className="px-3 py-2 text-right font-semibold">Itemized amount (USD)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {data.states.map((item) => (
                      <tr key={item.state ?? "unreported"}>
                        <th className="px-3 py-2 font-medium text-ink">
                          {item.state_full ?? item.state ?? "State not reported"}
                        </th>
                        <td className="px-3 py-2 text-right tabular-nums text-ink-soft">
                          {item.receipt_count.toLocaleString()}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-ink-soft">
                          {formatMoneyExact(item.amount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          <p className="text-xs text-ink-muted">
            Source: Federal Election Commission, Schedule A state aggregates. Retrieved{" "}
            {new Date(data.fetched_at).toLocaleString()}.
          </p>
        </>
      )}
    </div>
  );
}
