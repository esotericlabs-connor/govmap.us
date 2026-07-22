import type { Config } from "tailwindcss";

const config: Config = {
  // Must include components/ — Tailwind only generates classes it finds in
  // these globs, so anything outside them would render completely unstyled.
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Wired to next/font CSS variables set in app/layout.tsx.
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "sans-serif"],
      },
      colors: {
        // Sampled directly from the GovMap logo files so brand color never
        // drifts from the mark.
        govnavy: "#070B1A",
        "govnavy-800": "#0A0E1E", // the logo's own background / dark surfaces
        govred: "#DD1922",
        govblue: "#58A9E6",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
      animation: {
        // `both` fill-mode holds the 0% state through any animation-delay, so
        // staggered elements don't flash before their turn.
        "fade-up": "fade-up 0.7s cubic-bezier(0.22, 1, 0.36, 1) both",
        "fade-in": "fade-in 0.9s ease-out both",
      },
      boxShadow: {
        card: "0 1px 3px rgba(7,11,26,0.06), 0 12px 32px -16px rgba(7,11,26,0.22)",
      },
    },
  },
  plugins: [],
};

export default config;
