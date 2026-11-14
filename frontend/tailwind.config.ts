import type { Config } from "tailwindcss";
import colors from "tailwindcss/colors";
import plugin from "tailwindcss/plugin";

// Light/Dark theming. Every themeable color is an "r g b" CSS variable, so the
// same class (bg-white, text-govnavy, border-slate-warm-200, …) renders the
// right value in either theme and opacity modifiers like bg-govnavy/80 still
// work. Elements marked `.chrome` (menu, banners, footer, map status
// bar) always use the light values on their own dark navy backgrounds.

const SHADES = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"] as const;
type Shade = (typeof SHADES)[number];

// Dark mode reads a scale back to front: a pale tint becomes a deep tint with
// the same role (50 ↔ 950, 100 ↔ 900, …) and 500 stays put.
function mirror(shade: Shade): Shade {
  return SHADES[SHADES.length - 1 - SHADES.indexOf(shade)];
}

// Only the default palettes the app uses; add one here before using it.
const MIRRORED_PALETTES: Record<string, Record<Shade, string>> = {
  slate: colors.slate,
  red: colors.red,
  green: colors.green,
  emerald: colors.emerald,
  amber: colors.amber,
  violet: colors.violet,
};

const WARM_SHADES = ["50", "100", "200", "300", "400", "500", "600", "700", "800"] as const;

// Brand values are sampled from the GovMap logo files. Dark values keep body
// text at WCAG AA (4.5:1) or better on the dark card and page surfaces.
const THEMED: Record<string, { light: string; dark: string }> = {
  white: { light: "#FFFFFF", dark: "#111A2E" },
  govnavy: { light: "#070B1A", dark: "#EEF2FA" },
  govred: { light: "#DD1922", dark: "#F0565C" },
  "govblue-100": { light: "#EBF6FE", dark: "#0E2236" },
  "govblue-400": { light: "#89C5ED", dark: "#3F93D6" },
  "govblue-600": { light: "#3F93D6", dark: "#89C5ED" },
  "slate-warm-50": { light: "#F8F7F6", dark: "#0A0F1D" },
  "slate-warm-100": { light: "#F1F0EE", dark: "#151D31" },
  "slate-warm-200": { light: "#E4E2DE", dark: "#233049" },
  "slate-warm-300": { light: "#D6D3CB", dark: "#33425F" },
  "slate-warm-400": { light: "#A8A29E", dark: "#7C88A1" },
  "slate-warm-500": { light: "#78716C", dark: "#98A3B9" },
  "slate-warm-600": { light: "#57534E", dark: "#B3BCCD" },
  "slate-warm-700": { light: "#44403C", dark: "#CDD3DF" },
  "slate-warm-800": { light: "#292524", dark: "#E4E8F0" },
};

/** "#rrggbb" → "r g b", the form `rgb(var(--x) / <alpha-value>)` needs. */
function channels(hex: string): string {
  const match = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!match) throw new Error(`Theme colors must be #rrggbb; got ${hex}`);
  const n = Number.parseInt(match[1], 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
}

const lightVars: Record<string, string> = {};
const darkVars: Record<string, string> = {};
for (const [name, palette] of Object.entries(MIRRORED_PALETTES)) {
  for (const shade of SHADES) {
    lightVars[`--gm-${name}-${shade}`] = channels(palette[shade]);
    darkVars[`--gm-${name}-${shade}`] = channels(palette[mirror(shade)]);
  }
}
for (const [name, value] of Object.entries(THEMED)) {
  lightVars[`--gm-${name}`] = channels(value.light);
  darkVars[`--gm-${name}`] = channels(value.dark);
}

function themed(name: string): string {
  return `rgb(var(--gm-${name}) / <alpha-value>)`;
}

function themedScale(name: string, shades: readonly string[]): Record<string, string> {
  return Object.fromEntries(shades.map((shade) => [shade, themed(`${name}-${shade}`)]));
}

const themeVariables = plugin(({ addBase }) => {
  addBase({
    // No stored choice → follow the system setting (works without JS). An
    // explicit choice is the data-theme attribute set by lib/theme.mjs.
    ":root, .chrome": lightVars,
    ":root": { colorScheme: "light" },
    "@media (prefers-color-scheme: dark)": {
      ':root:not([data-theme="light"])': { ...darkVars, colorScheme: "dark" },
    },
    ':root[data-theme="dark"]': { ...darkVars, colorScheme: "dark" },
    // Separate rule so a browser without ::backdrop can't drop the ones above.
    // Dialog backdrops dim the page with navy in both themes.
    "::backdrop": lightVars,
  });
});

const config: Config = {
  // `dark:` follows the same rules as the variables: the system setting unless
  // a theme is chosen, and never inside the always-dark `.chrome` surfaces.
  darkMode: [
    "variant",
    [
      '@media (prefers-color-scheme: dark) { &:not([data-theme="light"] *):not(.chrome, .chrome *) }',
      '&:is([data-theme="dark"] *):not(.chrome, .chrome *)',
    ],
  ],
  // Tailwind only generates classes it finds in these globs, so anything
  // outside them would render completely unstyled. lib/ holds shared class maps.
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx,mjs}"],
  theme: {
    extend: {
      fontFamily: {
        // Wired to next/font CSS variables set in app/layout.tsx.
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "sans-serif"],
      },
      colors: {
        ...Object.fromEntries(
          Object.keys(MIRRORED_PALETTES).map((name) => [name, themedScale(name, SHADES)]),
        ),
        white: themed("white"),
        govnavy: themed("govnavy"),
        govred: themed("govred"),
        "govblue-100": themed("govblue-100"),
        "govblue-400": themed("govblue-400"),
        "govblue-600": themed("govblue-600"),
        "slate-warm": themedScale("slate-warm", WARM_SHADES),
        // Fixed in both themes: the banner navy and the logo blue.
        "govnavy-800": "#0A0E1E",
        govblue: "#58A9E6",
        // Semantic names for new dashboard surfaces; same variables as above.
        canvas: themed("slate-warm-50"),
        panel: themed("white"),
        sunken: themed("slate-warm-100"),
        line: themed("slate-warm-200"),
        ink: {
          DEFAULT: themed("govnavy"),
          soft: themed("slate-warm-600"),
          muted: themed("slate-warm-500"),
        },
        // Chart series. Mid-tones read on both themes, and none of them is a
        // party color, so a chamber or count is never mistaken for a party.
        series: {
          house: "#8B5CF6",
          senate: "#F59E0B",
          bills: "#10B981",
        },
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        // Slide only — no opacity change, so frosted/translucent children keep
        // their final density before, during, and after the entrance.
        rise: {
          "0%": { transform: "translateY(14px)" },
          "100%": { transform: "translateY(0)" },
        },
        // Pronounced hero entrance — starts fully transparent and eases in, so
        // the hero elements are clearly less visible at the start of page load.
        "hero-in": {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-down-and-fade": {
          "0%": { opacity: "0", transform: "translateY(-4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        ring: {
          "0%": {
            transform: "scale(.33)",
            opacity: "1",
          },
          "80%, 100%": {
            transform: "scale(1.4)",
            opacity: "0",
          },
        },
      },
      animation: {
        // `both` fill-mode holds the 0% state through any animation-delay, so
        // staggered elements don't flash before their turn.
        "fade-up": "fade-up 0.7s cubic-bezier(0.22, 1, 0.36, 1) both",
        // Keep content visible even during the delay or a restored scroll.
        // Drop the transform afterwards so fixed descendants stay viewport-bound.
        reveal: "rise 0.6s cubic-bezier(0.22, 1, 0.36, 1) backwards",
        rise: "rise 0.7s cubic-bezier(0.22, 1, 0.36, 1) both",
        "hero-in": "hero-in 1s cubic-bezier(0.22, 1, 0.36, 1) both",
        "fade-in": "fade-in 0.9s ease-out both",
        "subtle-fade-in": "fade-in 0.5s ease-out both",
        "slide-down-and-fade": "slide-down-and-fade 0.3s cubic-bezier(0.16, 1, 0.3, 1) both",
        ring: "ring 1.2s cubic-bezier(0.22, 1, 0.36, 1) both",
      },
      boxShadow: {
        card: "0 2px 8px rgba(7,11,26,0.05), 0 10px 24px -8px rgba(7,11,26,0.1)",
        "card-hover": "0 2px 8px rgba(7,11,26,0.08), 0 14px 32px -8px rgba(7,11,26,0.18)",
      },
      borderColor: {
        // Preflight's color for a bare `border`; a plain value because
        // theme() isn't relied on to fill in `<alpha-value>`.
        DEFAULT: "rgb(var(--gm-slate-warm-200))",
      },
    },
  },
  plugins: [themeVariables],
};

export default config;
