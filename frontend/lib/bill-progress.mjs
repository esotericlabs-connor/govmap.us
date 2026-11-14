/**
 * Where a bill or resolution stands in the legislative process, read only from
 * its official Congress.gov action log. Each step marked done cites the verbatim
 * action behind it, or says plainly that a later step implies it. Nothing is
 * predicted or summarized. Pure, so the bill page and the unit tests agree on
 * every rule.
 *
 * Congress.gov lists actions newest first and often records one event twice
 * (once by the chamber, once by the Library of Congress), so steps match the
 * earliest action with the expected wording instead of relying on list order.
 */

/**
 * @typedef {object} BillAction
 * @property {number} seq position in the source list (newest first)
 * @property {string | null} action_date ISO date
 * @property {string | null} chamber "House", "Senate" or null
 * @property {string} text verbatim Congress.gov action text
 * @property {string | null} action_type Congress.gov action type
 */

/**
 * @typedef {object} BillInput
 * @property {string} bill_type hr, s, hjres, sjres, hconres, sconres, hres or sres
 * @property {number} congress
 * @property {string | null} title
 * @property {string | null} introduced_date
 * @property {string | null} status "Became Law" when Congress.gov lists a law
 * @property {BillAction[]} actions
 * @property {number | null} [current_congress] the Congress GovMap tracks now
 */

/** @typedef {"done" | "current" | "upcoming" | "stopped" | "skipped" | "unreached"} StepState */

/**
 * @typedef {object} Step
 * @property {string} id
 * @property {string} label
 * @property {StepState} state
 * @property {string | null} date ISO date of the action behind this state
 * @property {string | null} source verbatim action text behind this state
 * @property {string | null} note plain explanation when the source alone doesn't say it
 */

/** @typedef {"enacted" | "agreed" | "stopped" | "ended" | "active" | "unknown"} Outcome */

/**
 * @typedef {object} BillProgress
 * @property {"bill" | "amendment" | "concurrent" | "simple"} kind
 * @property {string} noun
 * @property {Step[]} steps
 * @property {number} completed steps done or passed over
 * @property {Outcome} outcome
 * @property {string} headline where it stands, in a few words
 * @property {string | null} next what has to happen next, if anything can
 * @property {string[]} notes
 */

/** @typedef {"House" | "Senate"} Chamber */

const OVER_VETO = /\bover (?:the )?veto\b|objections of the President to the contrary notwithstanding/i;
const INTRODUCED = /^Introduced in (?:the )?(?:House|Senate)\b/i;
const REFERRED = /\breferred to\b/i;
const VETO_MESSAGE = /\bveto message\b/i;
const REPORTED = /^(?:Reported\b|(?:House |Senate )?Committee on [^.]+\.\s*Reported\b)/i;
const DISCHARGED = /^(?:House |Senate )?Committee on .+\bdischarged\b/i;
const PRESENTED = /^Presented to President\b/i;
const SIGNED = /^Signed by President\b/i;
const BECAME_LAW = /^Became (?:Public |Private )?Law\b/i;
const VETOED = /^(?:Pocket )?Vetoed by President\b/i;
const POCKET_VETOED = /^Pocket Vetoed\b/i;
const CLEARED = /^Cleared for White House\b/i;
const AMENDED = /\bwith (?:an )?amendments?\b|\bas amended\b/i;
const AMENDMENT_TITLE = /^Proposing (?:an amendment|amendments) to the Constitution\b/i;
const CONCURRED = /^(?:House agreed to Senate amendments?|Senate agreed to House amendments?|(?:House|Senate) concurred in (?:the )?(?:House|Senate) amendments?)\b/i;

/** @type {Record<Chamber, RegExp>} */
const PASSED = {
  House: /^(?:Passed\/agreed to in House|Passed House|(?:Concurrent )?Resolution agreed to in House)\b/i,
  Senate: /^(?:Passed\/agreed to in Senate|Passed Senate|(?:Concurrent )?Resolution agreed to in Senate)\b/i,
};

/** @type {Record<Chamber, RegExp>} */
const FAILED = {
  House: /^Failed of passage(?:\/not agreed to)? in House\b/i,
  Senate: /^Failed of passage(?:\/not agreed to)? in Senate\b/i,
};

/** @type {Record<Chamber, RegExp>} */
const CONFERENCE_AGREED = {
  House: /^Conference report agreed to in House\b/i,
  Senate: /^Conference report agreed to in Senate\b/i,
};

/**
 * "119th", "101st", "112th".
 * @param {number} n
 * @returns {string}
 */
export function ordinal(n) {
  const lastTwo = n % 100;
  if (lastTwo >= 11 && lastTwo <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

/**
 * @param {string} type lowercase bill type
 * @param {string | null} title
 * @returns {BillProgress["kind"]}
 */
function kindOf(type, title) {
  if (type === "hres" || type === "sres") return "simple";
  if (type === "hconres" || type === "sconres") return "concurrent";
  if ((type === "hjres" || type === "sjres") && AMENDMENT_TITLE.test(title ?? "")) return "amendment";
  return "bill";
}

/**
 * @param {string} type lowercase bill type
 * @returns {string}
 */
function nounOf(type) {
  if (type === "hres" || type === "sres") return "resolution";
  if (type === "hconres" || type === "sconres") return "concurrent resolution";
  if (type === "hjres" || type === "sjres") return "joint resolution";
  return "bill";
}

/**
 * Oldest first. Within one day a higher seq is the earlier action, because the
 * source lists newest first. Undated actions sort last.
 * @param {BillAction[]} actions
 * @returns {BillAction[]}
 */
function chronological(actions) {
  return [...actions].sort(
    (a, b) =>
      (a.action_date ?? "9999").localeCompare(b.action_date ?? "9999") || b.seq - a.seq,
  );
}

/**
 * @param {string} text
 * @returns {Chamber}
 */
function chamberNamed(text) {
  return PASSED.Senate.test(text) || FAILED.Senate.test(text) ? "Senate" : "House";
}

/**
 * @param {BillInput} bill
 * @returns {BillProgress}
 */
export function billProgress(bill) {
  const type = bill.bill_type.toLowerCase();
  /** @type {Chamber} */
  const origin = type.startsWith("s") ? "Senate" : "House";
  /** @type {Chamber} */
  const other = origin === "House" ? "Senate" : "House";
  const kind = kindOf(type, bill.title);
  const resolution = kind === "simple" || kind === "concurrent";
  const verb = resolution ? "Agreed to in" : "Passed";
  const twoThirds = kind === "amendment" ? " (two-thirds needed)" : "";
  const actions = chronological(bill.actions);

  /** @param {(a: BillAction) => boolean} test */
  const earliest = (test) => actions.find(test) ?? null;
  /** @param {RegExp} re */
  const says = (re) => (/** @type {BillAction} */ a) => re.test(a.text);
  /** @param {RegExp} re */
  const regular = (re) => (/** @type {BillAction} */ a) => re.test(a.text) && !OVER_VETO.test(a.text);

  const originPass = earliest(regular(PASSED[origin]));
  const originFail = originPass ? null : earliest(regular(FAILED[origin]));
  const otherPass = kind === "simple" ? null : earliest(regular(PASSED[other]));
  const otherFail = kind === "simple" || otherPass ? null : earliest(regular(FAILED[other]));

  // Committee work in the chamber of origin, before its floor vote. The other
  // chamber's referral comes later and is a different step.
  const originVote = originPass ?? originFail;
  /** @param {BillAction} a */
  const inOrigin = (a) =>
    (a.chamber === origin || a.chamber === null) &&
    !(originVote?.action_date && a.action_date && a.action_date > originVote.action_date);
  const referral = earliest((a) => inOrigin(a) && REFERRED.test(a.text) && !VETO_MESSAGE.test(a.text));
  const report = earliest((a) => inOrigin(a) && (REPORTED.test(a.text) || DISCHARGED.test(a.text)));

  const introduced = earliest(says(INTRODUCED));
  const presented = earliest(says(PRESENTED));
  const signed = earliest(says(SIGNED));
  const vetoed = earliest(says(VETOED));
  const lawAction = earliest(says(BECAME_LAW));
  const cleared = earliest(says(CLEARED));
  const enacted = kind === "bill" && (lawAction !== null || signed !== null || bill.status === "Became Law");
  const overridePasses = actions.filter(
    (a) => (PASSED.House.test(a.text) || PASSED.Senate.test(a.text)) && OVER_VETO.test(a.text),
  );
  const overrideFail = earliest(
    (a) => (FAILED.House.test(a.text) || FAILED.Senate.test(a.text)) && OVER_VETO.test(a.text),
  );
  // Only an unqualified agreement resolves differences; agreeing WITH a
  // further amendment sends the text back to the other chamber.
  const latestAgreement = [...actions].reverse().find(says(CONCURRED)) ?? null;
  const concurrence = latestAgreement &&
    !AMENDED.test(latestAgreement.text) &&
    (!otherPass || actions.indexOf(latestAgreement) > actions.indexOf(otherPass))
    ? latestAgreement
    : null;
  const conferenceHouse = earliest(says(CONFERENCE_AGREED.House));
  const conferenceSenate = earliest(says(CONFERENCE_AGREED.Senate));
  const conference = conferenceHouse && conferenceSenate
    ? chronological([conferenceHouse, conferenceSenate])[1]
    : null;
  const differencesEvidence = presented ?? signed ?? vetoed ?? lawAction ?? cleared ?? concurrence ?? conference;
  const differencesSettled =
    presented !== null ||
    signed !== null ||
    vetoed !== null ||
    enacted ||
    cleared !== null ||
    concurrence !== null ||
    conference !== null;
  const differencesPending =
    otherPass !== null && AMENDED.test(otherPass.text) && !differencesSettled;

  /** @type {{ id: string, label: string, hit: BillAction | null, reached: boolean, failure: BillAction | null }[]} */
  const plan = [
    {
      id: "introduced",
      label: "Introduced",
      hit: introduced,
      reached: bill.introduced_date !== null || actions.length > 0 || enacted,
      failure: null,
    },
    { id: "committee", label: "Committee", hit: report, reached: report !== null, failure: null },
    {
      id: "origin",
      label: `${verb} ${origin}`,
      hit: originPass,
      reached: originPass !== null,
      failure: originFail,
    },
  ];
  if (kind !== "simple") {
    plan.push({
      id: "other",
      label: `${verb} ${other}`,
      hit: otherPass,
      reached: otherPass !== null,
      failure: otherFail,
    });
  }
  if (otherPass && AMENDED.test(otherPass.text)) {
    plan.push({
      id: "differences",
      label: "Resolve differences",
      hit: differencesEvidence,
      reached: differencesSettled,
      failure: null,
    });
  }
  if (kind === "bill") {
    plan.push({
      id: "president",
      label: "To the President",
      hit: presented,
      reached: presented !== null || signed !== null || vetoed !== null || enacted,
      failure: null,
    });
    plan.push({
      id: "law",
      label: "Became law",
      hit: lawAction ?? signed,
      reached: enacted,
      failure: enacted ? null : vetoed,
    });
  }

  let lastReached = -1;
  plan.forEach((p, i) => {
    if (p.reached) lastReached = i;
  });
  // A failure counts only past the furthest step on record; an earlier one was
  // later overcome (for example, a vote reconsidered and passed).
  const failedAt = plan.findIndex((p, i) => i > lastReached && p.failure !== null);
  const settled = failedAt >= 0 ? failedAt - 1 : lastReached;
  const finished = failedAt < 0 && settled === plan.length - 1;
  const noHistory = actions.length === 0 && !enacted;
  const ended =
    !finished &&
    failedAt < 0 &&
    bill.current_congress != null &&
    bill.congress < bill.current_congress;
  const congressName = `${ordinal(bill.congress)} Congress`;

  /** @type {Step[]} */
  const steps = plan.map((p, i) => {
    const base = { id: p.id, label: p.label };
    if (i <= settled) {
      if (p.id === "introduced") {
        return {
          ...base,
          state: "done",
          date: bill.introduced_date ?? p.hit?.action_date ?? null,
          source: p.hit?.text ?? null,
          note: p.hit || !bill.introduced_date ? null : "Introduction date from the Congress.gov bill record.",
        };
      }
      if (p.reached && p.hit) {
        return { ...base, state: "done", date: p.hit.action_date, source: p.hit.text, note: null };
      }
      if (p.id === "committee") {
        return referral
          ? {
              ...base,
              state: "done",
              date: referral.action_date,
              source: referral.text,
              note: "Moved on without a committee report on file.",
            }
          : { ...base, state: "skipped", date: null, source: null, note: "No committee referral on file." };
      }
      if (p.id === "law") {
        return {
          ...base,
          state: "done",
          date: null,
          source: null,
          note: "Congress.gov lists this as an enacted law.",
        };
      }
      return { ...base, state: "done", date: null, source: null, note: "Implied by a later step on record." };
    }
    if (noHistory) return { ...base, state: "upcoming", date: null, source: null, note: null };
    if (i === failedAt && p.failure) {
      return { ...base, state: "stopped", date: p.failure.action_date, source: p.failure.text, note: null };
    }
    if (i === settled + 1 && failedAt < 0) {
      if (ended) {
        return {
          ...base,
          state: "stopped",
          date: null,
          source: null,
          note: `The ${congressName} ended before this step.`,
        };
      }
      if (p.id === "committee") {
        return referral
          ? {
              ...base,
              state: "current",
              date: referral.action_date,
              source: referral.text,
              note: "No committee report on file yet.",
            }
          : { ...base, state: "current", date: null, source: null, note: "No committee referral on file yet." };
      }
      return { ...base, state: "current", date: null, source: null, note: null };
    }
    return {
      ...base,
      state: failedAt >= 0 || ended ? "unreached" : "upcoming",
      date: null,
      source: null,
      note: null,
    };
  });

  /** @type {Outcome} */
  let outcome;
  let headline;
  /** @type {string | null} */
  let next = null;
  /** @type {string[]} */
  const notes = [];

  if (noHistory) {
    outcome = "unknown";
    headline = "No action history on file yet";
  } else if (failedAt >= 0) {
    outcome = "stopped";
    const step = plan[failedAt];
    if (step.id === "origin") headline = `Failed in the ${origin}`;
    else if (step.id === "other") headline = `Failed in the ${other}`;
    else if (vetoed && POCKET_VETOED.test(vetoed.text)) headline = "Pocket vetoed by the President";
    else if (overrideFail) headline = `Vetoed; the override failed in the ${chamberNamed(overrideFail.text)}`;
    else {
      headline = "Vetoed by the President";
      const overridden = new Set(overridePasses.map((a) => chamberNamed(a.text)));
      for (const chamber of overridden) notes.push(`The ${chamber} voted to override the veto.`);
      const remaining = /** @type {Chamber[]} */ (["House", "Senate"]).filter((c) => !overridden.has(c));
      if (bill.current_congress != null && bill.congress < bill.current_congress) {
        notes.push(`The ${congressName} ended without overriding the veto.`);
      } else if (remaining.length === 2) {
        next = "Congress can override the veto with a two-thirds vote in each chamber";
      } else if (remaining.length === 1) {
        next = `A two-thirds override vote in the ${remaining[0]}`;
      }
    }
    if (step.id === "origin" || step.id === "other") {
      notes.push("A failed passage vote can be reconsidered. This records the vote on file, not a prediction that the measure can never pass.");
    }
  } else if (finished) {
    if (kind === "bill") {
      outcome = "enacted";
      headline = overridePasses.length > 0 ? "Became law over the President's veto" : "Became law";
    } else if (kind === "amendment") {
      outcome = "agreed";
      headline = "Passed both chambers";
      next = "Ratification by three-fourths of the states, which GovMap doesn't track";
      notes.push("Constitutional amendments don't go to the President.");
    } else if (kind === "concurrent") {
      outcome = "agreed";
      headline = "Agreed to by both chambers";
      notes.push("Concurrent resolutions don't go to the President and don't have the force of law.");
    } else {
      outcome = "agreed";
      headline = `Agreed to by the ${origin}`;
      notes.push(
        `A simple resolution concerns only the ${origin}: it doesn't go to the ${other} or the President and doesn't have the force of law.`,
      );
    }
  } else if (ended) {
    outcome = "ended";
    headline = `Ended with the ${congressName}`;
    notes.push(
      "Bills and resolutions that don't finish within a Congress expire; they have to be introduced again to move.",
    );
  } else {
    outcome = "active";
    const step = plan[settled + 1];
    if (step.id === "committee") {
      headline = referral ? "In committee" : "Introduced";
      next = `Committee review, then a vote in the ${origin}${twoThirds}`;
    } else if (step.id === "origin") {
      headline = "Reported by committee";
      next = `A vote in the ${origin}${twoThirds}`;
    } else if (step.id === "other") {
      headline = `${resolution ? "Agreed to by" : "Passed"} the ${origin}`;
      next = `A vote in the ${other}${twoThirds}`;
    } else if (step.id === "differences") {
      headline = `${verb} both chambers in different versions`;
      next = kind === "bill"
        ? "Both chambers agree on identical text, then it goes to the President"
        : "Both chambers agree on identical text";
    } else if (step.id === "president") {
      headline = "Passed both chambers";
      next = "Presentment to the President";
    } else {
      headline = "With the President";
      next = "Presidential action or enactment without a signature under the constitutional time limits";
    }
  }

  if (differencesPending && (outcome === "active" || outcome === "ended")) {
    notes.push(
      `The ${other} passed it with changes, so both chambers must agree on identical text${
        kind === "bill" ? " before it can go to the President" : ""
      }.`,
    );
  }

  return {
    kind,
    noun: nounOf(type),
    steps,
    completed: steps.filter((s) => s.state === "done" || s.state === "skipped").length,
    outcome,
    headline,
    next,
    notes,
  };
}
