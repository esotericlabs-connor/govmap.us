/**
 * Bug-report categories → areas of the app. Mirrors the backend allowlist in
 * `app/report_categories.py` (the server validates against its copy, so this is
 * just the UI's source for the dropdowns). Keep the two in sync.
 */

export const REPORT_CATEGORIES: Record<string, string[]> = {
  Map: ["District / state map", "ZIP lookup"],
  Members: ["Profile", "Roster", "Search"],
  Finance: ["Campaign totals", "Itemized donations"],
  Bills: ["Bill detail", "Full text", "Bill list"],
  Votes: ["Vote detail", "Vote list"],
  Committees: ["Committee detail", "Meetings", "Referred bills"],
  Search: ["Universal search"],
  "Data accuracy": ["Wrong or missing data"],
  "Site / UI": ["Layout", "Performance", "Something else"],
  Other: ["Other"],
};

export const REPORT_CATEGORY_NAMES = Object.keys(REPORT_CATEGORIES);

/** Best guess at the category/subcategory for the page a reporter is on, so the
 *  form opens pre-filled to the right area. */
export function defaultCategoryForPath(pathname: string): { category: string; subcategory: string } {
  const at = (category: string, subcategory: string) => ({ category, subcategory });
  if (pathname.includes("/donations")) return at("Finance", "Itemized donations");
  if (pathname.startsWith("/congress")) return at("Map", "District / state map");
  if (pathname === "/members") return at("Members", "Roster");
  if (pathname.startsWith("/members")) return at("Members", "Profile");
  if (pathname.startsWith("/bills")) return at("Bills", "Bill detail");
  if (pathname.startsWith("/votes")) return at("Votes", "Vote detail");
  if (pathname.startsWith("/committees")) return at("Committees", "Committee detail");
  return at("Other", "Other");
}
