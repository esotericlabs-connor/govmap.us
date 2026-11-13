/** @param {string} query @param {string} text */
export function matchesListQuery(query, text) {
  const haystack = text.toLocaleLowerCase();
  const words = query.toLocaleLowerCase().replaceAll(",", " ").split(/\s+/).filter(Boolean);
  return words.length > 0 ? words.every((word) => haystack.includes(word)) : !query.trim();
}

/**
 * Missing values stay last in either direction; equal values retain source order.
 * @param {string | number | null | undefined} a
 * @param {string | number | null | undefined} b
 * @param {boolean} descending
 */
export function compareListValues(a, b, descending = false) {
  if (a === null || a === undefined || a === "") return b === null || b === undefined || b === "" ? 0 : 1;
  if (b === null || b === undefined || b === "") return -1;
  const result = typeof a === "number" && typeof b === "number"
    ? a - b
    : String(a).localeCompare(String(b), "en", { numeric: true, sensitivity: "base" });
  return descending ? -result : result;
}

/**
 * Preserve unrelated page state, but never retain an old result offset.
 * @param {string} current
 * @param {Iterable<[string, string]>} values
 * @param {string[]} managedNames
 * @param {Record<string, { name: string, value?: string }[]>} [requirements]
 */
export function listQuery(current, values, managedNames, requirements = {}) {
  const query = new URLSearchParams(current);
  for (const name of [...managedNames, "offset"]) query.delete(name);
  for (const [name, value] of values) {
    if (value.trim()) query.set(name, value.trim());
  }
  for (const [name, prerequisites] of Object.entries(requirements)) {
    if (prerequisites.some((required) => required.value === undefined
      ? !query.get(required.name)
      : query.get(required.name) !== required.value)) query.delete(name);
  }
  return query;
}

/**
 * @param {Record<string, string | string[] | undefined>} params
 * @param {string[]} sorts
 * @param {string} defaultSort
 */
export function readListQuery(params, sorts, defaultSort) {
  /** @param {string | string[] | undefined} value */
  const first = (value) => Array.isArray(value) ? value[0] : value;
  const q = first(params.q)?.trim() ?? "";
  const sort = first(params.sort) || defaultSort;
  const rawOffset = first(params.offset) ?? "0";
  const offset = Number(rawOffset);
  const invalid = q.length > 100 || !sorts.includes(sort)
    || !/^\d+$/.test(rawOffset) || !Number.isSafeInteger(offset) || offset < 0 || offset > 1_000_000;
  return { q, sort, offset, invalid };
}

/** @param {string} href @param {string} current */
export function listPageHref(href, current) {
  const next = new URL(href, "https://govmap.invalid");
  for (const [key, value] of new URLSearchParams(current)) {
    if (/_(q|sort|group)$/.test(key) && !next.searchParams.has(key)) next.searchParams.set(key, value);
  }
  return `${next.pathname}${next.search}${next.hash}`;
}

/** @param {string} current @param {string} id @param {string} key @param {string} value */
export function localListQuery(current, id, key, value) {
  const next = new URLSearchParams(current);
  if (value && !(key === "sort" && value === "source")) next.set(`${id}_${key}`, value);
  else next.delete(`${id}_${key}`);
  return next;
}

/**
 * An acknowledged URL write must not erase text typed after that write.
 * @param {{source: string, draft: string, submitted: string | null}} search
 * @param {string} source
 */
export function reconcileListSearch(search, source) {
  return { source, draft: search.submitted === source ? search.draft : source, submitted: null };
}
