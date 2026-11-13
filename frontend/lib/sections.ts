/**
 * The one registry of GovMap's sections. The menu and the search box's
 * "jump to" shortcuts both read it, so a destination is never live in one place
 * and missing (or invented) in another. Only mark a section "live" once its
 * page serves real data; planned sections point at the About coverage list.
 *
 * Kept import-free with erasable-only TypeScript so tests/sections.test.mjs can
 * load it directly under Node.
 */

export type SectionAvailability = "live" | "planned";
export type SectionGroup = "workspace" | "project";

export type Section = {
  id: string;
  label: string;
  href: string;
  description: string;
  keywords: readonly string[];
  group: SectionGroup;
  availability: SectionAvailability;
};

const COVERAGE_HREF = "/about#coverage";

export const SECTIONS: readonly Section[] = [
  {
    id: "overview",
    label: "Federal overview",
    href: "/",
    description: "All three federal branches at a glance",
    keywords: ["overview", "dashboard", "home", "federal", "branches", "summary", "at a glance"],
    group: "workspace",
    availability: "live",
  },
  {
    id: "map",
    label: "Congress map",
    href: "/map",
    description: "Every House and Senate seat, by district",
    keywords: ["map", "district", "seats", "house", "senate", "congress", "find my rep"],
    group: "workspace",
    availability: "live",
  },
  {
    id: "members",
    label: "Members of Congress",
    href: "/members",
    description: "All currently serving representatives and senators",
    keywords: ["members", "representatives", "reps", "senators", "legislators", "congressmen", "people"],
    group: "workspace",
    availability: "live",
  },
  {
    id: "bills",
    label: "Bills & resolutions",
    href: "/bills",
    description: "The most recently active legislation",
    keywords: ["bills", "legislation", "resolutions", "acts", "recent"],
    group: "workspace",
    availability: "live",
  },
  {
    id: "laws",
    label: "Recently enacted laws",
    href: "/bills?status=became-law",
    description: "Bills that became law, newest action first",
    keywords: ["laws", "enacted", "became law", "public law", "signed", "passed", "new laws"],
    group: "workspace",
    availability: "live",
  },
  {
    id: "votes",
    label: "Roll-call votes",
    href: "/votes",
    description: "Recent House and Senate floor votes",
    keywords: ["votes", "roll call", "roll-call", "yeas", "nays", "floor votes"],
    group: "workspace",
    availability: "live",
  },
  {
    id: "elections",
    label: "Elections",
    href: COVERAGE_HREF,
    description: "Official results and the incoming Congress",
    keywords: ["elections", "midterms", "results", "candidates", "members-elect", "incoming", "120th"],
    group: "workspace",
    availability: "planned",
  },
  {
    id: "money",
    label: "Campaign money",
    href: COVERAGE_HREF,
    description: "Contributions to candidates and from donors, by area",
    keywords: ["campaign", "money", "contributions", "donors", "fec", "finance", "fundraising"],
    group: "workspace",
    availability: "planned",
  },
  {
    id: "accountability",
    label: "Accountability",
    href: COVERAGE_HREF,
    description: "Sourced misconduct records and their outcomes",
    keywords: ["accountability", "misconduct", "ethics", "investigations", "allegations"],
    group: "workspace",
    availability: "planned",
  },
  {
    id: "executive",
    label: "Executive · White House & agencies",
    href: COVERAGE_HREF,
    description: "Presidential documents, agencies and leadership",
    keywords: ["executive", "white house", "president", "agencies", "cabinet", "executive orders", "federal register"],
    group: "workspace",
    availability: "planned",
  },
  {
    id: "judicial",
    label: "Judicial · Federal courts",
    href: COVERAGE_HREF,
    description: "Courts, judges, nominations and opinions",
    keywords: ["judicial", "courts", "judges", "supreme court", "opinions", "nominations"],
    group: "workspace",
    availability: "planned",
  },
  {
    id: "about",
    label: "About GovMap",
    href: "/about",
    description: "Mission, coverage and data sources",
    keywords: ["about", "mission", "coverage", "roadmap", "sources"],
    group: "project",
    availability: "live",
  },
  {
    id: "security",
    label: "Security & transparency",
    href: "/security",
    description: "Open source, public data and how we protect it",
    keywords: ["security", "transparency", "open source", "vulnerability"],
    group: "project",
    availability: "live",
  },
  {
    id: "privacy",
    label: "Privacy",
    href: "/privacy",
    description: "What GovMap stores and why",
    keywords: ["privacy", "data", "cookies"],
    group: "project",
    availability: "live",
  },
  {
    id: "support",
    label: "Support the project",
    href: "/support",
    description: "Help keep GovMap free and independent",
    keywords: ["support", "donate", "sponsor", "contribute", "ko-fi"],
    group: "project",
    availability: "live",
  },
];

export function normalizeQuery(query: string): string {
  return query.toLowerCase().replace(/\s+/g, " ").trim();
}

// 2 when a token starts a word of the haystack, 1 when it appears inside one, 0 otherwise.
function tokenScore(token: string, haystack: string): number {
  if (haystack.startsWith(token) || haystack.includes(` ${token}`)) return 2;
  return haystack.includes(token) ? 1 : 0;
}

/**
 * Sections for a search query. An empty query returns the live workspace
 * shortcuts in registry order. Otherwise every query word must match the
 * label, a keyword or the description. Live sections always come before
 * planned ones, so a shortcut leads somewhere that works today; within each,
 * label matches outrank keyword matches, which outrank description matches.
 */
export function matchSections(query: string, limit = 5, sections: readonly Section[] = SECTIONS): Section[] {
  const q = normalizeQuery(query);
  if (!q) {
    return sections
      .filter((s) => s.group === "workspace" && s.availability === "live")
      .slice(0, limit);
  }
  const tokens = q.split(" ");
  const ranked: { section: Section; live: number; score: number; order: number }[] = [];
  sections.forEach((section, order) => {
    const label = section.label.toLowerCase();
    const keywords = section.keywords.join(" | ").toLowerCase();
    const description = section.description.toLowerCase();
    let score = 0;
    for (const token of tokens) {
      const best = Math.max(
        tokenScore(token, label) * 3,
        tokenScore(token, keywords) * 2,
        tokenScore(token, description),
      );
      if (best === 0) return;
      score += best;
    }
    ranked.push({ section, live: section.availability === "live" ? 1 : 0, score, order });
  });
  ranked.sort((a, b) => b.live - a.live || b.score - a.score || a.order - b.order);
  return ranked.slice(0, limit).map((r) => r.section);
}
