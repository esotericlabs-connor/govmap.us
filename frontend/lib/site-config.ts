/**
 * Single source of truth for cross-zone URLs and external links, so they're
 * never hardcoded in more than one place. Only real, owned accounts belong
 * here — the UI renders whatever is listed. See CODE-MANIFEST.md.
 */

export const siteConfig = {
  name: "GovMap.us",
  tagline: "From City Council to Congress.",

  // The app is the site: govmap.us opens straight to the map. /congress is a
  // permanent redirect to / (next.config.mjs) so old links keep working.
  appUrl: "/",

  githubUrl: "https://github.com/esotericlabs-connor/govmap.us",

  // Active donation platforms. `icon` maps to a glyph in
  // components/BrandIcon.tsx.
  supportLinks: [
    { label: "Ko-fi", href: "https://ko-fi.com/govmapus", icon: "kofi" },
    { label: "Buy Me a Coffee", href: "https://buymeacoffee.com/govmapus", icon: "buymeacoffee" },
    { label: "Liberapay", href: "https://liberapay.com/govmapus", icon: "liberapay" },
  ] as { label: string; href: string; icon: string }[],

  // Official GovMap accounts. `icon` maps to a glyph in components/BrandIcon.tsx.
  socialLinks: [
    { label: "Mastodon", href: "https://mastodon.social/@govmapus", icon: "mastodon" },
    { label: "Bluesky", href: "https://bsky.app/profile/govmapus.bsky.social", icon: "bluesky" },
    { label: "Instagram", href: "https://instagram.com/govmapus", icon: "instagram" },
  ] as { label: string; href: string; icon: string }[],

  contactEmail: "support@govmap.us" as string | null,
};
