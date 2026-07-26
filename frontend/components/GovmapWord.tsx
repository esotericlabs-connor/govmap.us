/**
 * The "govmap.us" wordmark with brand-colored segments — red "gov", blue ".us",
 * and "map" inheriting the surrounding text color. Server-safe (no hooks), so it
 * drops into both server and client components (buttons, links, etc.).
 */
export function GovmapWord() {
  return (
    <>
      <span className="text-govred">gov</span>map<span className="text-govblue">.us</span>
    </>
  );
}
