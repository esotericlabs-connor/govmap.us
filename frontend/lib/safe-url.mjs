/**
 * Outbound links rendered from upstream government data. Only absolute http(s)
 * URLs become hrefs, so a malformed or hostile stored value (for example a
 * `javascript:` or `data:` URL) can never become a clickable script link.
 *
 * @param {string | null | undefined} url
 * @returns {string | undefined}
 */
export function externalHref(url) {
  if (!url) return undefined;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}
