import Image from "next/image";
import Link from "next/link";

import { BrandIcon } from "@/components/BrandIcon";
import { siteConfig } from "@/lib/site-config";

type FooterLink = { label: string; href: string; external?: boolean };

const EXPLORE: FooterLink[] = [
  { label: "Enter GovMap", href: "/members" },
  { label: "Members of Congress", href: "/members" },
];

const PROJECT: FooterLink[] = [
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
      <h3 className="text-xs font-semibold uppercase tracking-wider text-white/50">
        {title}
      </h3>
      <ul className="mt-4 space-y-3">
        {links.map((link) => (
          <li key={link.label}>
            <a
              href={link.href}
              {...(link.external ? { target: "_blank", rel: "noreferrer" } : {})}
              className="text-sm text-white/70 transition-colors hover:text-white"
            >
              {link.label}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SiteFooter() {
  return (
    <footer className="relative isolate overflow-hidden bg-govnavy">
      {/* Capitol backdrop, dimmed and anchored to the bottom edge. */}
      <div
        className="absolute inset-0 -z-10 bg-cover bg-bottom opacity-40"
        style={{ backgroundImage: "url('/capitol-hero.jpg')" }}
        aria-hidden="true"
      />
      <div
        className="absolute inset-0 -z-10 bg-gradient-to-t from-govnavy via-govnavy/90 to-govnavy/70"
        aria-hidden="true"
      />

      <div className="mx-auto max-w-6xl px-6 pb-10 pt-16">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <Link href="/" aria-label="GovMap.us home">
              <Image src="/logo-dark-transparent.png" alt="GovMap.us" width={150} height={48} />
            </Link>
            <p className="mt-3 text-sm text-white/60">{siteConfig.tagline}</p>
            <div className="mt-5 flex gap-4">
              {siteConfig.socialLinks.map((social) => (
                <a
                  key={social.label}
                  href={social.href}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={social.label}
                  className="text-white/60 transition-colors hover:text-white"
                >
                  <BrandIcon name={social.icon} className="h-5 w-5" />
                </a>
              ))}
            </div>
          </div>

          <FooterCol title="Explore" links={EXPLORE} />
          <FooterCol title="Project" links={PROJECT} />
          <FooterCol title="Legal" links={LEGAL} />
        </div>

        <div className="mt-12 flex flex-col gap-2 border-t border-white/10 pt-6 text-xs text-white/45 sm:flex-row sm:items-center sm:justify-between">
          <p>
            © {new Date().getFullYear()} GovMap.us — a nonprofit, nonpartisan civic
            project.
          </p>
          <p>Data only, always sourced.</p>
        </div>
      </div>
    </footer>
  );
}
