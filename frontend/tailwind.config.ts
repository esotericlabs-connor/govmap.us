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
        "govnavy-800": "#0A0E1E",
        govred: "#DD1922",
        govblue: "#58A9E6",
        "govblue-100": "#EBF6FE",
        "govblue-400": "#89C5ED",
        "govblue-600": "#3F93D6",
        "slate-warm": {
          50: "#f8f7f6",
          100: "#f1f0ee",
          200: "#e4e2de",
          300: "#d6d3cb",
          400: "#a8a29e",
          500: "#78716c",
          600: "#57534e",
          700: "#44403c",
          800: "#292524",
        },
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
        "fade-in": "fade-in 0.9s ease-out both",
        "subtle-fade-in": "fade-in 0.5s ease-out both",
        "slide-down-and-fade": "slide-down-and-fade 0.3s cubic-bezier(0.16, 1, 0.3, 1) both",
        ring: "ring 1.2s cubic-bezier(0.22, 1, 0.36, 1) both",
      },
      boxShadow: {
        card: "0 2px 8px rgba(7,11,26,0.05), 0 10px 24px -8px rgba(7,11,26,0.1)",
        "card-hover": "0 2px 8px rgba(7,11,26,0.08), 0 14px 32px -8px rgba(7,11,26,0.18)",
      },
    },
  },
  plugins: [],
};

export default config;
