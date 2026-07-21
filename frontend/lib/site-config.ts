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

  // Where the marketing site's "Enter GovMap" button sends people, and
  // where the platform links back to. Same-zone links inside each app
  // should stay relative ("/", "/members") -- only cross-zone links need
  // an absolute URL, since govmap.us and app.govmap.us are different hosts.
  appUrl: process.env.NEXT_PUBLIC_APP_URL || "http://app.localhost:3000",
  marketingUrl: process.env.NEXT_PUBLIC_MARKETING_URL || "http://localhost:3000",

  githubUrl: "https://github.com/esotericlabs-connor/govmap.us",

  // TODO: fill in once accounts exist -- do not add placeholder/fake links.
  socialLinks: [] as { label: string; href: string }[],
  supportUrl: null as string | null,
  contactEmail: null as string | null,
};
