import Link from "next/link";
import type { ReactNode } from "react";

import { BannerCard, PageBanner } from "@/components/PageBanner";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { siteConfig } from "@/lib/site-config";

export const metadata = {
  title: "About",
  description:
    "Why GovMap exists, what it covers today, and where it's going — from city council to Congress.",
};

type Coverage = {
  name: string;
  status: "live" | "planned";
  what: string;
};

// Only mark a layer "live" once its data is actually served by the app.
const FEDERAL: Coverage[] = [
  {
    name: "Legislative · Congress",
    status: "live",
    what:
      "Every member of the House and Senate, the bills they sponsor, how they vote, the committees they sit on, and where their campaign money comes from. Find yours by ZIP code.",
  },
  {
    name: "Executive · The White House & agencies",
    status: "planned",
    what:
      "The President, Vice President and Cabinet, who runs each department and agency, executive orders from the Federal Register, and where federal money is spent.",
  },
  {
    name: "Judicial · The federal courts",
    status: "planned",
    what:
      "Supreme Court justices and federal judges, the opinions they publish, and court challenges to the laws Congress passes.",
  },
];

const BEYOND: Coverage[] = [
  {
    name: "State government",
    status: "planned",
    what:
      "Your governor, your state legislators, the bills moving through your statehouse, and how your state lawmakers vote.",
  },
  {
    name: "Local government",
    status: "planned",
    what:
      "City councils, county boards and the local offices that decide your roads, schools, zoning and taxes — the government closest to you.",
  },
];

const PRINCIPLES: { title: string; body: string }[] = [
  {
    title: "Nonpartisan, always",
    body: "No party, no candidate, no cause. Every official is shown the same way, with the same data.",
  },
  {
    title: "Records, not opinions",
    body: "No editorializing and no spin. Every fact links back to the official source it came from.",
  },
  {
    title: "No AI-written content",
    body: "Bill summaries come from the Congressional Research Service, Congress's own nonpartisan researchers. We don't generate or rewrite them.",
  },
  {
    title: "Plain English",
    body: "Clear labels instead of legislative jargon, so anyone can follow what's happening.",
  },
  {
    title: "Built for your phone",
    body: "Most people check on their government in a spare minute. GovMap is designed mobile-first.",
  },
  {
    title: "Open by default",
    body: "The code and the methods are public. Anyone can see exactly how the data is gathered and shown.",
  },
];

const SOURCES: { name: string; use: string }[] = [
  { name: "Congress.gov (Library of Congress)", use: "Bills, actions, cosponsors and committee meetings" },
  { name: "Congressional Research Service", use: "Official bill summaries" },
  { name: "GovInfo (U.S. Government Publishing Office)", use: "Full bill text" },
  { name: "Clerk of the House & U.S. Senate", use: "Roll-call votes" },
  { name: "Voteview (UCLA)", use: "Backup source for Senate roll-call votes" },
  { name: "Federal Election Commission", use: "Campaign finance and donations" },
  { name: "unitedstates/congress-legislators", use: "Member and committee records" },
  { name: "HUD USPS ZIP crosswalk", use: "Matching your ZIP code to your district" },
];

const linkClass = "font-semibold text-govblue-600 hover:underline";

function StatusBadge({ status }: { status: Coverage["status"] }) {
  return status === "live" ? (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
      Live now
    </span>
  ) : (
    <span className="inline-flex rounded-full bg-slate-warm-100 px-2.5 py-0.5 text-xs font-semibold text-slate-warm-600">
      Planned
    </span>
  );
}

function CoverageCard({ item }: { item: Coverage }) {
  return (
    <div className="flex h-full flex-col rounded-2xl border border-slate-warm-200 bg-white p-6 shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-display text-lg font-bold text-govnavy">{item.name}</h3>
        <StatusBadge status={item.status} />
      </div>
      <p className="mt-3 leading-relaxed text-slate-warm-600">{item.what}</p>
    </div>
  );
}

function SectionHeading({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="max-w-3xl">
      <p className="text-sm font-semibold uppercase tracking-wider text-govblue-600">{eyebrow}</p>
      <h2 className="mt-2 font-display text-3xl font-bold tracking-tight text-govnavy sm:text-4xl">
        {title}
      </h2>
      {children && <div className="mt-4 text-lg leading-relaxed text-slate-warm-600">{children}</div>}
    </div>
  );
}

export default function AboutPage() {
  return (
    <>
      <SiteHeader />
      <main className="bg-white">
        <PageBanner eyebrow="About GovMap" title={siteConfig.tagline}>
          <p>
            GovMap is a free, nonpartisan map of who governs you — every branch,
            every level, in one place. Real public records, always sourced. No
            ads, no spin, no AI-written summaries.
          </p>
        </PageBanner>

        {/* Mission + ambition */}
        <section className="mx-auto max-w-6xl px-6 py-20 sm:py-24">
          <div className="grid gap-12 lg:grid-cols-5">
            <div className="lg:col-span-3">
              <SectionHeading eyebrow="Why we built it" title="Apathy is largely a UX problem.">
                <p>
                  The information about who represents you, and what they do with
                  that power, is public — but it&apos;s scattered across dozens of
                  government websites, each with its own jargon, formats and dead
                  ends. Most people never find it, so most people never look.
                </p>
                <p className="mt-4">
                  GovMap pulls those official records together, connects them, and
                  presents them so anyone can understand them in a minute on their
                  phone. When the facts are easy to see, it&apos;s easier to take
                  part.
                </p>
              </SectionHeading>
            </div>
            <BannerCard className="lg:col-span-2">
              <p className="text-sm font-semibold uppercase tracking-wider text-white/60">
                The ambition
              </p>
              <p className="mt-3 font-display text-2xl font-bold leading-snug">
                One map of American government — from your city council to Congress.
              </p>
              <p className="mt-4 leading-relaxed text-white/80">
                Every official who represents you, every vote they cast, and every
                law as it moves from a proposal, through signature or veto, to any
                challenge in court — connected, and tied to where you live.
              </p>
            </BannerCard>
          </div>
        </section>

        {/* Coverage */}
        <section className="bg-slate-warm-50">
          <div className="mx-auto max-w-6xl px-6 py-20 sm:py-24">
            <SectionHeading
              eyebrow="How GovMap covers government"
              title="All three branches, then every level."
            >
              <p>
                We&apos;re building GovMap one layer at a time and only publish a
                layer once its data is complete and reliable. Here&apos;s exactly
                what&apos;s live today and what&apos;s coming next.
              </p>
            </SectionHeading>

            <h3 className="mt-12 text-sm font-semibold uppercase tracking-wider text-slate-warm-500">
              Federal government
            </h3>
            <div className="mt-4 grid gap-6 md:grid-cols-3">
              {FEDERAL.map((item) => (
                <CoverageCard key={item.name} item={item} />
              ))}
            </div>

            <h3 className="mt-12 text-sm font-semibold uppercase tracking-wider text-slate-warm-500">
              Closer to home
            </h3>
            <div className="mt-4 grid gap-6 md:grid-cols-2">
              {BEYOND.map((item) => (
                <CoverageCard key={item.name} item={item} />
              ))}
            </div>

            <BannerCard className="mt-12">
              <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
                <div className="max-w-2xl">
                  <h3 className="font-display text-xl font-bold">
                    The full life of a law, in one view
                  </h3>
                  <p className="mt-2 leading-relaxed text-white/80">
                    Our signature goal is a single timeline that follows a bill from
                    introduction in Congress, through the President&apos;s signature
                    or veto, to any judicial challenge — connecting all three
                    branches the way they actually work together.
                  </p>
                </div>
                <Link
                  href="/"
                  className="shrink-0 self-start rounded-full bg-white px-6 py-3 font-semibold text-govnavy shadow-lg transition-transform duration-200 hover:-translate-y-0.5 sm:self-center"
                >
                  Explore the map →
                </Link>
              </div>
            </BannerCard>
          </div>
        </section>

        {/* Principles */}
        <section className="mx-auto max-w-6xl px-6 py-20 sm:py-24">
          <SectionHeading eyebrow="Our principles" title="Rules we don't bend." />
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {PRINCIPLES.map((p) => (
              <div key={p.title} className="rounded-2xl border border-slate-warm-200 p-6">
                <h3 className="font-display text-lg font-bold text-govnavy">{p.title}</h3>
                <p className="mt-2 leading-relaxed text-slate-warm-600">{p.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Sources */}
        <section className="bg-slate-warm-50">
          <div className="mx-auto max-w-6xl px-6 py-20 sm:py-24">
            <SectionHeading
              eyebrow="Where the data comes from"
              title="Official sources, linked every time."
            >
              <p>
                Everything GovMap shows today comes from these public sources. Each
                record links back to where it came from, so you can check it
                yourself.
              </p>
            </SectionHeading>
            <ul className="mt-10 grid gap-x-8 gap-y-5 sm:grid-cols-2">
              {SOURCES.map((s) => (
                <li key={s.name} className="border-l-2 border-govblue pl-4">
                  <p className="font-semibold text-govnavy">{s.name}</p>
                  <p className="text-sm text-slate-warm-600">{s.use}</p>
                </li>
              ))}
            </ul>
            <p className="mt-10 text-slate-warm-600">
              How we gather, check and protect this data is documented in the open —
              read our{" "}
              <Link href="/security" className={linkClass}>
                security &amp; transparency
              </Link>{" "}
              page or browse the{" "}
              <a href={siteConfig.githubUrl} target="_blank" rel="noreferrer" className={linkClass}>
                source code on GitHub
              </a>
              .
            </p>
          </div>
        </section>

        {/* Get involved */}
        <section className="mx-auto max-w-6xl px-6 py-20 sm:py-24">
          <div className="grid gap-6 md:grid-cols-2">
            <BannerCard>
              <h3 className="font-display text-xl font-bold">Keep GovMap independent</h3>
              <p className="mt-2 leading-relaxed text-white/80">
                No ads and no political money. GovMap runs on small donations from
                people who think this should exist.
              </p>
              <Link
                href="/support"
                className="mt-6 inline-flex rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-govnavy transition-transform duration-200 hover:-translate-y-0.5"
              >
                Support the project →
              </Link>
            </BannerCard>
            <div className="rounded-2xl border border-slate-warm-200 p-6 sm:p-8">
              <h3 className="font-display text-xl font-bold text-govnavy">Say hello</h3>
              <p className="mt-2 leading-relaxed text-slate-warm-600">
                Spotted something wrong, or want to help build it? Use{" "}
                <em>Report a problem</em> in the menu, open an issue on GitHub, or
                reach us directly.
              </p>
              <ul className="mt-4 space-y-2 text-sm">
                {siteConfig.contactEmail && (
                  <li>
                    <a href={`mailto:${siteConfig.contactEmail}`} className={linkClass}>
                      {siteConfig.contactEmail}
                    </a>
                  </li>
                )}
                {siteConfig.socialLinks.map((s) => (
                  <li key={s.label}>
                    <a href={s.href} target="_blank" rel="noreferrer" className={linkClass}>
                      {s.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
