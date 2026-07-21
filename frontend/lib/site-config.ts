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
  // the platform at /members etc. These are plain relative paths. The
  // app.govmap.us subdomain split is deferred until the base app is stable —
  // see CODE-MANIFEST.md.
  appUrl: "/members",
  marketingUrl: "/",

  githubUrl: "https://github.com/esotericlabs-connor/govmap.us",

  // TODO: fill in once accounts exist -- do not add placeholder/fake links.
  socialLinks: [] as { label: string; href: string }[],
  supportUrl: null as string | null,
  contactEmail: null as string | null,
};
