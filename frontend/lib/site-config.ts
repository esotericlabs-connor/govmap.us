/**
 * Single source of truth for cross-zone URLs and external links, so they're
 * never hardcoded in more than one place. Values that don't exist yet
 * (social handles, a support/donation link) are left null/empty rather than
 * filled with placeholders — the UI only renders what's actually real. Fill
 * them in here as accounts/links go live; see CODE-MANIFEST.md.
 */

export const siteConfig = {
  name: "GovMap.us",
  tagline: "From City Council to Congress.",

  // Marketing and platform now live on one host (govmap.us): marketing at /,
  // the platform at /congress (the dashboard entry), /members etc. These are
  // plain relative paths. The app.govmap.us subdomain split is deferred until
  // the base app is stable — see CODE-MANIFEST.md.
  appUrl: "/congress",
  marketingUrl: "/",

  githubUrl: "https://github.com/esotericlabs-connor/govmap.us",

  // Active donation/support platforms. `icon` maps to a glyph in
  // components/BrandIcon.tsx.
  supportLinks: [
    { label: "Patreon", href: "https://www.patreon.com/govmapus", icon: "patreon" },
    { label: "Ko-fi", href: "https://ko-fi.com/govmapus", icon: "kofi" },
    { label: "Buy Me a Coffee", href: "https://buymeacoffee.com/govmapus", icon: "buymeacoffee" },
    { label: "Liberapay", href: "https://liberapay.com/govmapus", icon: "liberapay" },
    { label: "Open Collective", href: "https://opencollective.com/connorremsen", icon: "opencollective" },
    { label: "thanks.dev", href: "https://thanks.dev/gh/esotericlabs-connor", icon: "thanksdev" },
  ] as { label: string; href: string; icon: string }[],

  // Placeholder handles (@govmapus) — accounts to be claimed; links resolve
  // once they are. `icon` maps to a glyph in components/BrandIcon.tsx.
  socialLinks: [
    { label: "X", href: "https://x.com/govmapus", icon: "x" },
    { label: "Bluesky", href: "https://bsky.app/profile/govmapus.bsky.social", icon: "bluesky" },
    { label: "Instagram", href: "https://instagram.com/govmapus", icon: "instagram" },
  ] as { label: string; href: string; icon: string }[],

  contactEmail: null as string | null,
};
