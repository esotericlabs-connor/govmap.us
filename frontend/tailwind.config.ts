import type { Config } from "tailwindcss";

const config: Config = {
  // Must include components/ — Tailwind only generates classes it finds in
  // these globs, so anything outside them (e.g. MemberAvatar) would render
  // completely unstyled.
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Sampled directly from the GovMap logo files (public/logo-dark.png,
        // public/logo-light.png) so brand color never drifts from the mark.
        govnavy: "#070B1A",
        govred: "#DD1922",
        govblue: "#58A9E6",
      },
    },
  },
  plugins: [],
};

export default config;
