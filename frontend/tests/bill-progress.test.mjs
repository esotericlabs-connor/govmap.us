import assert from "node:assert/strict";
import { test } from "node:test";

import { billProgress, ordinal } from "../lib/bill-progress.mjs";

/**
 * An action log in Congress.gov order: newest first, seq = list position.
 * @param {...[string | null, string | null, string]} rows date, chamber, text
 */
function log(...rows) {
  return rows.map(([action_date, chamber, text], seq) => ({
    seq,
    action_date,
    chamber,
    text,
    action_type: null,
  }));
}

/** @param {Partial<import("../lib/bill-progress.mjs").BillInput>} fields */
function bill(fields) {
  return {
    bill_type: "hr",
    congress: 119,
    title: "A bill",
    introduced_date: null,
    status: null,
    actions: [],
    current_congress: 119,
    ...fields,
  };
}

/** @param {import("../lib/bill-progress.mjs").BillProgress} progress */
const states = (progress) => progress.steps.map((s) => s.state);

const INTRODUCED_HOUSE = log(
  ["2026-03-02", "House", "Referred to the House Committee on Energy and Commerce."],
  ["2026-03-02", null, "Introduced in House"],
);

// H.R. 3076 (117th), abridged: discharged from committee, passed both
// chambers, signed.
const ENACTED = bill({
  congress: 117,
  introduced_date: "2021-05-13",
  status: "Became Law",
  actions: log(
    ["2022-04-06", null, "Became Public Law No: 117-108."],
    ["2022-04-06", null, "Signed by President."],
    ["2022-04-06", null, "Presented to President."],
    ["2022-03-08", "Senate", "Passed Senate without amendment by Yea-Nay Vote. 79 - 19. Record Vote Number: 71."],
    [
      "2022-03-08",
      null,
      "Passed/agreed to in Senate: Passed Senate without amendment by Yea-Nay Vote. 79 - 19. Record Vote Number: 71.",
    ],
    ["2022-02-08", null, "Passed/agreed to in House: On passage Passed by the Yeas and Nays: 342 - 92 (Roll no. 38)."],
    ["2022-02-07", "House", "Rules Committee Resolution H. Res. 912 Reported to House."],
    ["2022-02-01", "House", "Committee on Ways and Means discharged."],
    ["2021-05-13", "House", "Referred to the Committee on Oversight and Reform, and in addition to the Committee on Ways and Means."],
    ["2021-05-13", null, "Introduced in House"],
  ),
});

test("an enacted bill completes every step, each citing its source action", () => {
  const p = billProgress(ENACTED);
  assert.equal(p.kind, "bill");
  assert.equal(p.noun, "bill");
  assert.deepEqual(
    p.steps.map((s) => s.label),
    ["Introduced", "Committee", "Passed House", "Passed Senate", "To the President", "Became law"],
  );
  assert.deepEqual(states(p), ["done", "done", "done", "done", "done", "done"]);
  assert.equal(p.completed, 6);
  assert.equal(p.outcome, "enacted");
  assert.equal(p.headline, "Became law");
  assert.equal(p.next, null);
  assert.equal(p.steps[0].date, "2021-05-13");
  assert.equal(p.steps[1].source, "Committee on Ways and Means discharged.");
  assert.equal(p.steps[2].date, "2022-02-08");
  assert.match(p.steps[3].source ?? "", /^Passed\/agreed to in Senate/);
  assert.equal(p.steps[5].source, "Became Public Law No: 117-108.");
});

test("the result doesn't depend on the order actions arrive in", () => {
  const reversed = { ...ENACTED, actions: [...ENACTED.actions].reverse() };
  assert.deepEqual(billProgress(reversed), billProgress(ENACTED));
});

test("a referred bill is in committee", () => {
  const p = billProgress(bill({ introduced_date: "2026-03-02", actions: INTRODUCED_HOUSE }));
  assert.deepEqual(states(p), ["done", "current", "upcoming", "upcoming", "upcoming", "upcoming"]);
  assert.equal(p.steps[1].date, "2026-03-02");
  assert.equal(p.steps[1].note, "No committee report on file yet.");
  assert.equal(p.outcome, "active");
  assert.equal(p.headline, "In committee");
  assert.equal(p.next, "Committee review, then a vote in the House");
  assert.equal(p.completed, 1);
});

test("a rule passing the House is not the bill passing", () => {
  const p = billProgress(
    bill({
      actions: [
        ...log(["2026-04-08", "House", "Rule H. Res. 327 passed House."]),
        ...INTRODUCED_HOUSE.map((a) => ({ ...a, seq: a.seq + 1 })),
      ],
    }),
  );
  assert.equal(p.steps[2].state, "upcoming");
  assert.equal(p.headline, "In committee");
});

test("after the House passes it, the Senate is next", () => {
  const p = billProgress(
    bill({
      actions: log(
        ["2026-04-10", "Senate", "Received in the Senate and Read twice and referred to the Committee on Finance."],
        [
          "2026-04-09",
          null,
          "Passed/agreed to in House: On motion to suspend the rules and pass the bill Agreed to by the Yeas and Nays: 400 - 20 (Roll no. 120).",
        ],
        ["2026-03-02", "House", "Referred to the House Committee on Energy and Commerce."],
        ["2026-03-02", null, "Introduced in House"],
      ),
    }),
  );
  assert.deepEqual(states(p), ["done", "done", "done", "current", "upcoming", "upcoming"]);
  // Referred but never reported: the House still voted, so the step is behind it.
  assert.equal(p.steps[1].source, "Referred to the House Committee on Energy and Commerce.");
  assert.equal(p.steps[1].note, "Moved on without a committee report on file.");
  assert.equal(p.headline, "Passed the House");
  assert.equal(p.next, "A vote in the Senate");
  assert.equal(p.completed, 3);
});

// H.J.Res. 39 (118th): vetoed, House override failed.
test("a veto with a failed override stops at the last step", () => {
  const p = billProgress(
    bill({
      bill_type: "hjres",
      congress: 118,
      title: "Providing for congressional disapproval under chapter 8 of title 5, United States Code, of the rule submitted by the Department of Commerce",
      actions: log(
        [
          "2023-05-24",
          "House",
          "On motion to refer the bill and the accompanying veto message to the Committee on Ways and Means. Agreed to without objection.",
        ],
        [
          "2023-05-24",
          null,
          "Failed of passage in House over veto On passage, the objections of the President to the contrary notwithstanding Failed by the Yeas and Nays: (2/3 required): 214 - 205 (Roll no. 233).",
        ],
        ["2023-05-16", null, "Vetoed by President."],
        ["2023-05-09", null, "Presented to President."],
        [
          "2023-05-03",
          null,
          "Passed/agreed to in Senate: Passed Senate without amendment by Yea-Nay Vote. 56 - 41. Record Vote Number: 109.",
        ],
        ["2023-05-01", "Senate", "Received in the Senate, read twice."],
        ["2023-04-28", null, "Passed/agreed to in House: On passage Passed by the Yeas and Nays: 221 - 202 (Roll no. 202)."],
        ["2023-04-26", "House", "Rule H. Res. 327 passed House."],
        ["2023-04-21", null, "Reported by the Committee on Ways and Means. H. Rept. 118-38."],
        ["2023-03-07", "House", "Referred to the House Committee on Ways and Means."],
        ["2023-03-07", null, "Introduced in House"],
      ),
    }),
  );
  assert.equal(p.noun, "joint resolution");
  assert.deepEqual(states(p), ["done", "done", "done", "done", "done", "stopped"]);
  assert.equal(p.steps[1].source, "Reported by the Committee on Ways and Means. H. Rept. 118-38.");
  assert.equal(p.steps[5].source, "Vetoed by President.");
  assert.equal(p.outcome, "stopped");
  assert.equal(p.headline, "Vetoed; the override failed in the House");
  assert.equal(p.next, null);
  assert.equal(p.completed, 5);
});

test("a veto awaiting the second override vote names that chamber", () => {
  const p = billProgress(
    bill({
      actions: log(
        [
          "2026-08-03",
          null,
          "Passed House over veto: Two-thirds of the Members present having voted in the affirmative the bill is passed, the objections of the President to the contrary notwithstanding.",
        ],
        ["2026-07-28", null, "Vetoed by President."],
        ["2026-07-20", null, "Presented to President."],
        ["2026-07-10", null, "Passed/agreed to in Senate: Passed Senate without amendment by Unanimous Consent."],
        ["2026-06-10", null, "Passed/agreed to in House: On passage Passed by the Yeas and Nays: 300 - 120 (Roll no. 150)."],
        ["2026-05-01", null, "Introduced in House"],
      ),
    }),
  );
  assert.deepEqual(states(p), ["done", "skipped", "done", "done", "done", "stopped"]);
  assert.equal(p.steps[1].note, "No committee referral on file.");
  // The override vote is not the original passage.
  assert.equal(p.steps[2].date, "2026-06-10");
  assert.equal(p.headline, "Vetoed by the President");
  assert.deepEqual(p.notes, ["The House voted to override the veto."]);
  assert.equal(p.next, "A two-thirds override vote in the Senate");
});

test("a pocket veto has no next step", () => {
  const p = billProgress(
    bill({
      actions: log(
        ["2026-12-20", null, "Pocket Vetoed by President."],
        ["2026-12-01", null, "Presented to President."],
        ["2026-11-20", null, "Passed/agreed to in Senate: Passed Senate without amendment by Voice Vote."],
        ["2026-09-10", null, "Passed/agreed to in House: On passage Passed by voice vote."],
        ["2026-05-01", null, "Introduced in House"],
      ),
    }),
  );
  assert.equal(p.steps[5].state, "stopped");
  assert.equal(p.headline, "Pocket vetoed by the President");
  assert.equal(p.next, null);
});

// H.R. 6395 (116th), abridged: conference, veto, override in both chambers.
test("a veto overridden by both chambers became law", () => {
  const p = billProgress(
    bill({
      congress: 116,
      status: "Became Law",
      actions: log(
        ["2021-01-01", null, "Became Public Law No: 116-283."],
        [
          "2021-01-01",
          null,
          "Passed Senate over veto: Passed Senate over veto by Yea-Nay Vote. 81 - 13. Record Vote Number: 292.",
        ],
        [
          "2020-12-28",
          null,
          "Passed House over veto: Two-thirds of the Members present having voted in the affirmative the bill is passed, the objections of the President to the contrary notwithstanding.",
        ],
        ["2020-12-23", null, "Vetoed by President."],
        ["2020-12-11", null, "Presented to President."],
        [
          "2020-12-11",
          null,
          "Conference report agreed to in Senate: Senate agreed to conference report by Yea-Nay Vote. 84 - 13. Record Vote Number: 264.",
        ],
        [
          "2020-12-08",
          null,
          "Conference report agreed to in House: On agreeing to the conference report Agreed to by the Yeas and Nays: 335 - 78, 1 Present (Roll no. 238).",
        ],
        ["2020-11-16", null, "Passed/agreed to in Senate: Passed Senate with an amendment by Voice Vote."],
        ["2020-07-21", null, "Passed/agreed to in House: On passage Passed by the Yeas and Nays: 295 - 125 (Roll no. 152)."],
        ["2020-07-09", null, "Reported (Amended) by the Committee on Armed Services. H. Rept. 116-442."],
        ["2020-03-26", "House", "Referred to the House Committee on Armed Services."],
        ["2020-03-26", null, "Introduced in House"],
      ),
    }),
  );
  assert.deepEqual(states(p), ["done", "done", "done", "done", "done", "done", "done"]);
  assert.equal(p.steps[2].date, "2020-07-21");
  assert.equal(p.steps[3].date, "2020-11-16");
  assert.equal(p.outcome, "enacted");
  assert.equal(p.headline, "Became law over the President's veto");
  assert.deepEqual(p.notes, []);
});

test("a failed vote in the first chamber stops the bill there", () => {
  const p = billProgress(
    bill({
      actions: [
        ...log([
          "2026-05-12",
          null,
          "Failed of passage/not agreed to in House: On motion to suspend the rules and pass the bill Failed by the Yeas and Nays: (2/3 required): 250 - 170 (Roll no. 140).",
        ]),
        ...INTRODUCED_HOUSE.map((a) => ({ ...a, seq: a.seq + 1 })),
      ],
    }),
  );
  assert.deepEqual(states(p), ["done", "done", "stopped", "unreached", "unreached", "unreached"]);
  assert.equal(p.steps[2].date, "2026-05-12");
  assert.equal(p.outcome, "stopped");
  assert.equal(p.headline, "Failed in the House");
  assert.equal(p.next, null);
  assert.equal(p.completed, 2);
});

test("a simple resolution ends in its own chamber", () => {
  const p = billProgress(
    bill({
      bill_type: "sres",
      title: "A resolution designating June 2026 as National Example Month.",
      actions: log(
        [
          "2026-06-01",
          null,
          "Passed/agreed to in Senate: Submitted in the Senate, considered, and agreed to without amendment and with a preamble by Unanimous Consent.",
        ],
        ["2026-06-01", null, "Introduced in Senate"],
      ),
    }),
  );
  assert.equal(p.kind, "simple");
  assert.equal(p.noun, "resolution");
  assert.deepEqual(
    p.steps.map((s) => s.label),
    ["Introduced", "Committee", "Agreed to in Senate"],
  );
  assert.deepEqual(states(p), ["done", "skipped", "done"]);
  assert.equal(p.outcome, "agreed");
  assert.equal(p.headline, "Agreed to by the Senate");
  assert.equal(p.completed, 3);
  assert.match(p.notes[0], /doesn't go to the House or the President/);
});

test("a concurrent resolution needs both chambers but not the President", () => {
  const p = billProgress(
    bill({
      bill_type: "hconres",
      actions: log(
        ["2026-02-05", null, "Passed/agreed to in Senate: Resolution agreed to in Senate without amendment by Unanimous Consent."],
        ["2026-02-04", null, "Passed/agreed to in House: On agreeing to the resolution Agreed to without objection."],
        ["2026-02-04", null, "Introduced in House"],
      ),
    }),
  );
  assert.equal(p.kind, "concurrent");
  assert.equal(p.steps.length, 4);
  assert.equal(p.steps[3].label, "Agreed to in Senate");
  assert.equal(p.outcome, "agreed");
  assert.equal(p.headline, "Agreed to by both chambers");
  assert.match(p.notes[0], /don't go to the President/);
});

test("a constitutional amendment needs two-thirds and goes to the states", () => {
  const introduced = billProgress(
    bill({
      bill_type: "hjres",
      title: "Proposing an amendment to the Constitution of the United States relative to the term of office.",
      actions: INTRODUCED_HOUSE,
    }),
  );
  assert.equal(introduced.kind, "amendment");
  assert.equal(introduced.steps.length, 4);
  assert.equal(introduced.next, "Committee review, then a vote in the House (two-thirds needed)");

  const passed = billProgress(
    bill({
      bill_type: "sjres",
      title: "Proposing an amendment to the Constitution of the United States relative to the term of office.",
      actions: log(
        ["2026-09-01", null, "Passed/agreed to in House: On passage Passed by the Yeas and Nays: (2/3 required): 300 - 120 (Roll no. 200)."],
        ["2026-07-01", null, "Passed/agreed to in Senate: Passed Senate without amendment by Yea-Nay Vote. 70 - 30."],
        ["2026-03-01", null, "Introduced in Senate"],
      ),
    }),
  );
  assert.equal(passed.steps[2].label, "Passed Senate");
  assert.equal(passed.outcome, "agreed");
  assert.equal(passed.headline, "Passed both chambers");
  assert.match(passed.next ?? "", /three-fourths of the states/);
});

test("a Congress.gov law listing alone marks it enacted without inventing dates", () => {
  const p = billProgress(bill({ status: "Became Law", introduced_date: "2025-01-03" }));
  assert.deepEqual(states(p), ["done", "skipped", "done", "done", "done", "done"]);
  assert.equal(p.steps[0].date, "2025-01-03");
  assert.equal(p.steps[2].date, null);
  assert.equal(p.steps[2].note, "Implied by a later step on record.");
  assert.equal(p.steps[5].note, "Congress.gov lists this as an enacted law.");
  assert.equal(p.outcome, "enacted");
});

test("no action history is reported honestly", () => {
  const p = billProgress(bill({ introduced_date: "2026-01-05" }));
  assert.deepEqual(states(p), ["done", "upcoming", "upcoming", "upcoming", "upcoming", "upcoming"]);
  assert.equal(p.outcome, "unknown");
  assert.equal(p.headline, "No action history on file yet");
  assert.equal(p.next, null);
  assert.equal(p.completed, 1);
});

test("an unfinished bill from an earlier Congress has ended", () => {
  const p = billProgress(
    bill({
      congress: 118,
      actions: log(
        ["2024-04-09", null, "Passed/agreed to in House: On passage Passed by voice vote."],
        ["2024-03-02", "House", "Referred to the House Committee on Energy and Commerce."],
        ["2024-03-02", null, "Introduced in House"],
      ),
    }),
  );
  assert.deepEqual(states(p), ["done", "done", "done", "stopped", "unreached", "unreached"]);
  assert.equal(p.steps[3].note, "The 118th Congress ended before this step.");
  assert.equal(p.outcome, "ended");
  assert.equal(p.headline, "Ended with the 118th Congress");
  assert.equal(p.next, null);
});

test("passing the second chamber with changes means the versions must match first", () => {
  const actions = log(
    ["2026-07-15", null, "Passed/agreed to in Senate: Passed Senate with an amendment by Unanimous Consent."],
    [
      "2026-06-10",
      null,
      "Passed/agreed to in House: On motion to suspend the rules and pass the bill, as amended Agreed to by voice vote.",
    ],
    ["2026-05-01", "House", "Referred to the House Committee on Natural Resources."],
    ["2026-05-01", null, "Introduced in House"],
  );
  const pending = billProgress(bill({ actions }));
  assert.deepEqual(states(pending), ["done", "done", "done", "done", "current", "upcoming", "upcoming"]);
  assert.equal(pending.steps[4].label, "Resolve differences");
  assert.equal(pending.headline, "Passed both chambers in different versions");
  assert.equal(pending.next, "Both chambers agree on identical text, then it goes to the President");
  assert.deepEqual(pending.notes, [
    "The Senate passed it with changes, so both chambers must agree on identical text before it can go to the President.",
  ]);

  const cleared = billProgress(
    bill({
      actions: [
        ...log(["2026-07-20", null, "Cleared for White House."]),
        ...actions.map((a) => ({ ...a, seq: a.seq + 1 })),
      ],
    }),
  );
  assert.equal(cleared.headline, "Passed both chambers");
  assert.equal(cleared.next, "Presentment to the President");
  assert.deepEqual(cleared.notes, []);
});

test("a bill sent to the President is with the President", () => {
  const p = billProgress(
    bill({
      bill_type: "s",
      actions: log(
        ["2026-09-02", null, "Presented to President."],
        ["2026-08-01", null, "Passed/agreed to in House: On motion to suspend the rules and pass the bill Agreed to by voice vote."],
        ["2026-06-01", null, "Passed/agreed to in Senate: Passed Senate without amendment by Unanimous Consent."],
        ["2026-05-01", "Senate", "Read twice and referred to the Committee on Finance."],
        ["2026-05-01", null, "Introduced in Senate"],
      ),
    }),
  );
  assert.deepEqual(
    p.steps.map((s) => s.label),
    ["Introduced", "Committee", "Passed Senate", "Passed House", "To the President", "Became law"],
  );
  assert.deepEqual(states(p), ["done", "done", "done", "done", "done", "current"]);
  assert.equal(p.headline, "With the President");
  assert.match(p.next ?? "", /enactment without a signature/);
});

test("missing dates and actions do not produce a completed milestone", () => {
  const p = billProgress(bill({}));
  assert.equal(p.outcome, "unknown");
  assert.equal(p.completed, 0);
  assert.ok(p.steps.every((s) => s.state === "upcoming"));
});

test("an official signature establishes enactment even before the law number arrives", () => {
  const p = billProgress(bill({
    actions: log(["2026-08-01", null, "Signed by President."]),
  }));
  assert.equal(p.outcome, "enacted");
  const last = p.steps.at(-1);
  assert.equal(last?.state, "done");
  assert.equal(last?.date, "2026-08-01");
  assert.equal(last?.source, "Signed by President.");
});

const AMENDED_CONCURRENT = log(
  ["2026-07-02", "Senate", "Passed Senate with an amendment by Unanimous Consent."],
  ["2026-07-01", "House", "Passed House by voice vote."],
  ["2026-06-01", null, "Introduced in House"],
);

test("a concurrent resolution with unresolved differences is not complete", () => {
  const p = billProgress(bill({ bill_type: "hconres", actions: AMENDED_CONCURRENT }));
  assert.equal(p.outcome, "active");
  assert.equal(p.steps.at(-1)?.id, "differences");
  assert.equal(p.steps.at(-1)?.state, "current");
  assert.ok(p.completed < p.steps.length);
  assert.equal(p.next, "Both chambers agree on identical text");
  assert.ok(p.steps.every((s) => s.id !== "president" && s.id !== "law"));
});

test("unqualified concurrence resolves differences with a cited action", () => {
  const agreement = "House agreed to Senate amendment by voice vote.";
  const p = billProgress(bill({
    bill_type: "hconres",
    actions: [
      ...log(["2026-07-03", "House", agreement]),
      ...AMENDED_CONCURRENT.map((a) => ({ ...a, seq: a.seq + 1 })),
    ],
  }));
  assert.equal(p.outcome, "agreed");
  assert.equal(p.steps.at(-1)?.source, agreement);
  assert.equal(p.steps.at(-1)?.state, "done");
});

test("a further amendment is not treated as final concurrence", () => {
  const p = billProgress(bill({
    bill_type: "hconres",
    actions: [
      ...log(["2026-07-03", "House", "House agreed to Senate amendment with an amendment by voice vote."]),
      ...AMENDED_CONCURRENT.map((a) => ({ ...a, seq: a.seq + 1 })),
    ],
  }));
  assert.equal(p.outcome, "active");
  assert.equal(p.steps.at(-1)?.state, "current");
});

test("unresolved differences do not keep an earlier Congress resolution active", () => {
  const p = billProgress(bill({
    bill_type: "hconres",
    congress: 118,
    actions: AMENDED_CONCURRENT.map((a) => ({
      ...a, action_date: a.action_date?.replace("2026", "2024") ?? null,
    })),
  }));
  assert.equal(p.outcome, "ended");
  assert.equal(p.steps.at(-1)?.state, "stopped");
});

test("a later successful vote supersedes a failed passage attempt", () => {
  const p = billProgress(bill({
    actions: log(
      ["2026-07-02", "House", "Passed House by voice vote."],
      ["2026-07-01", "House", "Failed of passage in House by the Yeas and Nays."],
      ["2026-06-01", null, "Introduced in House"],
    ),
  }));
  assert.equal(p.outcome, "active");
  assert.equal(p.headline, "Passed the House");
  assert.equal(p.steps[2].date, "2026-07-02");
});

test("ordinals", () => {
  assert.deepEqual(
    [1, 2, 3, 4, 11, 12, 13, 101, 111, 112, 113, 119, 121, 122, 123].map(ordinal),
    ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "101st", "111th", "112th", "113th", "119th", "121st", "122nd", "123rd"],
  );
});
