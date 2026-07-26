import Image from "next/image";
import Link from "next/link";

import { BrandIcon } from "@/components/BrandIcon";
import { BugReport } from "@/components/BugReport";
import { siteConfig } from "@/lib/site-config";

type FooterLink = { label: string; href: string; external?: boolean };

const EXPLORE: FooterLink[] = [
  { label: "Home", href: "/" },
  { label: "Congress", href: "/congress" },
  { label: "Members", href: "/members" },
];

const PROJECT: FooterLink[] = [
  { label: "About", href: "/#about" },
  { label: "Support", href: "/#support" },
  { label: "GitHub", href: siteConfig.githubUrl, external: true },
];

const LEGAL: FooterLink[] = [
  { label: "Privacy Policy", href: "/privacy" },
  { label: "Security", href: "/security" },
];

function FooterCol({ title, links }: { title: string; links: FooterLink[] }) {
  return (
    <div>
      <h3 className="text-sm font-semibold uppercase tracking-wider text-white/60">
        {title}
      </h3>
      <ul className="mt-4 space-y-3">
        {links.map((link) => (
          <li key={link.label}>
            <Link
              href={link.href}
              {...(link.external ? { target: "_blank", rel: "noreferrer" } : {})}
              className="text-white/80 transition-colors hover:text-white"
            >
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SiteFooter() {
  return (
    <footer className="relative isolate overflow-hidden bg-govnavy-800 text-sm">
      {/* Capitol backdrop — the photo is meant to show here; the scrim only
          dims it enough to keep the light text readable. Dial the /70 to taste. */}
      <div
        className="absolute inset-0 -z-10 bg-cover"
        style={{ backgroundImage: "url('/capitol-hero.jpg')", backgroundPosition: "center 40%" }}
        aria-hidden="true"
      />
      <div className="absolute inset-0 -z-10 bg-govnavy/70" aria-hidden="true" />

      <div className="mx-auto max-w-6xl px-6 pb-10 pt-20">
        <div className="grid gap-12 sm:grid-cols-2 lg:grid-cols-4">
          <div className="max-w-xs">
            <Link href="/" aria-label="GovMap.us home">
              <Image src="/logo-dark-transparent.png" alt="GovMap.us" width={150} height={48} />
            </Link>
            <p className="mt-4 text-white/70">{siteConfig.tagline}</p>
            <div className="mt-6 flex gap-5">
              {siteConfig.socialLinks.map((social) => (
                <a
                  key={social.label}
                  href={social.href}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={social.label}
                  className="text-white/70 transition-colors hover:text-white"
                >
                  <BrandIcon name={social.icon} className="h-5 w-5" />
                </a>
              ))}
              {/* Placeholder support address until a real inbox is provisioned. */}
              <a
                href="mailto:support@govmap.us"
                aria-label="Email GovMap.us"
                className="text-white/70 transition-colors hover:text-white"
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.9"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="h-5 w-5"
                  aria-hidden="true"
                >
                  <rect x="2.5" y="4.5" width="19" height="15" rx="2.5" />
                  <path d="m3 7 9 6 9-6" />
                </svg>
              </a>
            </div>
          </div>

          <FooterCol title="Explore" links={EXPLORE} />
          <FooterCol title="Project" links={PROJECT} />
          <FooterCol title="Legal" links={LEGAL} />
        </div>

        <div className="mt-16 flex flex-col gap-3 border-t border-white/10 pt-8 text-white/50 sm:flex-row sm:items-center sm:justify-between">
          <p>© {new Date().getFullYear()} GovMap.us — a nonprofit, nonpartisan civic project.</p>
          <div className="flex items-center gap-5">
            <BugReport triggerClassName="transition-colors hover:text-white" />
            <p>Data only, always sourced.</p>
          </div>
        </div>
      </div>
    </footer>
  );
}
