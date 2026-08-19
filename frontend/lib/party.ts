/**
 * Single source of truth for turning a source party string into a party key and
 * its brand colors. Sources spell the party out ("Democrat", "Republican", ...);
 * everything downstream keys off D / R / I. Pure + server-safe (no hooks / DOM).
 */

export type PartyKey = "D" | "R" | "I";

/** Democrat -> D, Republican -> R, everything else (including null) -> I. */
export function getPartyKey(party?: string | null): PartyKey {
  if (!party) return "I";
  if (party.startsWith("Democrat")) return "D";
  if (party.startsWith("Republican")) return "R";
  return "I";
}

// Party -> Tailwind text / dot / fill classes; brand hues come from the theme.
export const PARTY_COLORS: Record<PartyKey, { base: string; dot: string; fill: string }> = {
  D: { base: "text-govblue", dot: "bg-govblue", fill: "fill-govblue" },
  R: { base: "text-govred", dot: "bg-govred", fill: "fill-govred" },
  I: { base: "text-slate-500", dot: "bg-slate-400", fill: "fill-slate-400" },
};
