/**
 * Light/Dark theme preference, shared by the first-paint script in
 * app/layout.tsx and the useTheme hook. With no stored choice the CSS follows
 * the system setting; an explicit choice is mirrored onto <html data-theme>.
 */

/** @typedef {"system" | "light" | "dark"} ThemeChoice */
/** @typedef {"light" | "dark"} Theme */

export const THEME_STORAGE_KEY = "govmap_theme";

/** @type {readonly ThemeChoice[]} */
export const THEME_CHOICES = Object.freeze(["system", "light", "dark"]);

/**
 * A stored or attribute value as a choice; anything unexpected means "system".
 * @param {unknown} value
 * @returns {ThemeChoice}
 */
export function parseThemeChoice(value) {
  return value === "light" || value === "dark" ? value : "system";
}

/**
 * @param {ThemeChoice} choice
 * @param {boolean} prefersDark
 * @returns {Theme}
 */
export function resolveTheme(choice, prefersDark) {
  if (choice === "system") return prefersDark ? "dark" : "light";
  return choice;
}

/**
 * Runs inline in <head> before first paint, so a saved choice never flashes the
 * other theme. Storage can be blocked (private modes, policies); the page then
 * simply follows the system setting. A future nonce-based CSP must cover it.
 */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}})()`;
