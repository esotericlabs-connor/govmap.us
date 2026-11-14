import Link from "next/link";

import { BrandIcon } from "@/components/BrandIcon";
import { BannerCard, PageBanner } from "@/components/PageBanner";
import { SiteFooter } from "@/components/SiteFooter";
import { siteConfig } from "@/lib/site-config";

export const metadata = {
  title: "Support",
  description: "Help keep GovMap free, nonpartisan and independent — no ads, no political money.",
};

const WHERE_IT_GOES = [
  "Servers, storage and off-site backups that keep the site up and the data safe",
  "Time to add the next layers: the Executive branch, the courts, then state and local government",
  "Keeping every feature free for everyone — no paywalls, no ads, no data sales",
];

export default function SupportPage() {
  return (
    <>
      <main className="bg-white">
        <PageBanner eyebrow="Support GovMap" title="Keep it free. Keep it independent.">
          <p>
            GovMap takes no advertising and no political money. 
            The core of our platform will always remain free to the public. 
            We wouldn't be able to do this without your support.
          </p>
        </PageBanner>

        <section className="mx-auto max-w-6xl px-6 py-20 sm:py-24">
          <h2 className="font-display text-3xl font-bold tracking-tight text-govnavy">
            Chip in
          </h2>
          <p className="mt-3 max-w-2xl text-lg text-slate-warm-600">
            One-time or recurring — pick whichever platform you already use.
          </p>
          <div className="mt-10 grid gap-4 sm:grid-cols-3">
            {siteConfig.supportLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                target="_blank"
                rel="noreferrer"
                className="group flex items-center gap-4 rounded-2xl border border-slate-warm-200 bg-white p-5 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-govblue-400 hover:shadow-card-hover"
              >
                <BrandIcon
                  name={link.icon}
                  className="h-8 w-8 shrink-0 text-slate-400 transition-colors group-hover:text-govblue"
                />
                <span className="font-semibold text-govnavy">{link.label}</span>
                <span className="ml-auto text-slate-warm-400 transition-transform group-hover:translate-x-0.5">
                  ↗
                </span>
              </a>
            ))}
          </div>

          <div className="mt-16 grid gap-6 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-warm-200 p-6 sm:p-8">
              <h3 className="font-display text-xl font-bold text-govnavy">Where it goes</h3>
              <ul className="mt-4 space-y-3 text-slate-warm-600">
                {WHERE_IT_GOES.map((item) => (
                  <li key={item} className="flex gap-3">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-govblue" aria-hidden="true" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            <BannerCard>
              <h3 className="font-display text-xl font-bold">Other ways to help</h3>
              <p className="mt-2 leading-relaxed text-white/80">
                Share GovMap with someone who&apos;d use it, report anything that looks
                wrong, or contribute code — the whole project is open source.
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <a
                  href={siteConfig.githubUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-govnavy transition-transform duration-200 hover:-translate-y-0.5"
                >
                  GitHub ↗
                </a>
                <Link
                  href="/about"
                  className="inline-flex rounded-full border border-white/30 bg-white/10 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-white/20"
                >
                  About GovMap
                </Link>
              </div>
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
              </div>
            </BannerCard>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
