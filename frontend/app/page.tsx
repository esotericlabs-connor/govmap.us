import Image from "next/image";

import { BrandIcon } from "@/components/BrandIcon";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { siteConfig } from "@/lib/site-config";

const BRANCHES = [
  {
    name: "Legislative",
    covers: "535 members of Congress, bills, votes, committees, campaign finance, lobbying",
    cadence: "Every 30 min in session, daily otherwise",
  },
  {
    name: "Executive",
    covers: "President, VP, Cabinet, 15 departments, agency heads, executive orders",
    cadence: "Weekly sync + daily Federal Register feed",
  },
  {
    name: "Judicial",
    covers: "9 SCOTUS justices, 179 circuit judges, 677 district judges, opinions",
    cadence: "As opinions are published",
  },
];

const PRINCIPLES = [
  "Nonpartisan above all else",
  "Data only — no editorializing, no spin",
  "Plain English, no jargon",
  "Mobile-first",
  "Open methodology, publicly documented",
  "All three branches, equal pillars",
];

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" className="h-5 w-5 shrink-0 text-govblue" aria-hidden="true">
      <path
        d="M5 10.5L8.5 14L15 6.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function MarketingHomePage() {
  return (
    <>
      <SiteHeader variant="marketing" />

      <main>
        {/* Hero */}
        <section className="relative isolate overflow-hidden bg-govnavy">
          <Image
            src="/capitol-hero.jpg"
            alt=""
            fill
            priority
            sizes="100vw"
            className="-z-10 object-cover object-center"
          />
          <div className="absolute inset-0 -z-10 bg-gradient-to-r from-govnavy via-govnavy/85 to-transparent" />
          <div className="absolute inset-0 -z-10 bg-gradient-to-t from-govnavy via-govnavy/40 to-transparent" />

          <div className="mx-auto w-full max-w-6xl px-6 pb-24 pt-32 sm:pb-32 sm:pt-44">
            <h1 className="max-w-3xl animate-fade-up font-display text-4xl font-bold leading-[1.05] tracking-tight text-white [text-shadow:0_2px_20px_rgba(0,0,0,0.6)] sm:text-6xl lg:text-7xl">
              See your <span className="text-govred">government.</span>{" "}
              <span className="text-[#5cb3ff]">Clearly.</span>
            </h1>
            <p
              className="mt-6 max-w-xl animate-fade-up text-lg font-medium leading-relaxed text-white [text-shadow:0_1px_14px_rgba(0,0,0,0.6)] sm:text-xl"
              style={{ animationDelay: "120ms" }}
            >
              GovMap is a nonpartisan, end-to-end live-synced view of the entire
              US federal government — who represents you, how they vote, who runs
              the agencies that govern you, where the money goes, and how a bill
              becomes law. Real data, always sourced. No press. No spin.
            </p>
            <div
              className="mt-9 flex flex-wrap items-center gap-4 animate-fade-up"
              style={{ animationDelay: "240ms" }}
            >
              <a
                href={siteConfig.appUrl}
                className="rounded-full bg-govblue px-7 py-3.5 font-semibold text-govnavy shadow-lg shadow-govblue/20 transition hover:-translate-y-0.5 hover:bg-white"
              >
                Enter GovMap →
              </a>
              <a
                href="#about"
                className="rounded-full border border-white/30 px-7 py-3.5 font-semibold text-white/90 transition hover:border-white/70 hover:bg-white/5"
              >
                How it works
              </a>
            </div>
          </div>
        </section>

        {/* About */}
        <section id="about" className="scroll-mt-24 bg-white">
          <div className="mx-auto max-w-6xl px-6 py-24">
          <Reveal>
            <h2 className="font-display text-3xl font-bold text-govnavy sm:text-4xl">
              One nonpartisan view of all three branches
            </h2>
            <p className="mt-4 max-w-2xl text-slate-600">
              Most civic tools stop at Congress. GovMap treats the Legislative,
              Executive, and Judicial branches as equal pillars — and connects
              them: a bill&apos;s full journey from introduction, through
              signature or veto, through any judicial challenge, in a single
              timeline. No other civic tool currently shows all three stages in
              one view.
            </p>
          </Reveal>

          <div className="mt-12 grid gap-6 sm:grid-cols-3">
            {BRANCHES.map((branch, i) => (
              <Reveal key={branch.name} delay={i * 100} className="h-full">
                <div className="h-full rounded-xl border border-slate-200 bg-white p-6 shadow-card transition duration-300 hover:-translate-y-1 hover:shadow-lg">
                  <h3 className="font-display font-semibold text-govnavy">{branch.name}</h3>
                  <p className="mt-2 text-sm text-slate-600">{branch.covers}</p>
                  <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-govblue">
                    {branch.cadence}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>

          <Reveal className="mt-14">
            <div className="rounded-xl bg-slate-50 p-8">
              <h3 className="font-display font-semibold text-govnavy">
                Built on a few rules we don&apos;t bend
              </h3>
              <ul className="mt-4 grid gap-3 sm:grid-cols-2">
                {PRINCIPLES.map((principle) => (
                  <li key={principle} className="flex items-start gap-2 text-sm text-slate-700">
                    <CheckIcon />
                    <span>{principle}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
          </div>
        </section>

        {/* Support */}
        <section id="support" className="scroll-mt-24 bg-slate-50">
          <div className="mx-auto max-w-6xl px-6 py-24">
            <Reveal>
              <h2 className="font-display text-3xl font-bold text-govnavy sm:text-4xl">
                Support GovMap
              </h2>
              <p className="mt-4 max-w-2xl text-slate-600">
                GovMap is a nonprofit, nonpartisan civic tool — no advertising,
                no political funding. It runs on donations and the time of
                people who believe transparent government tooling should exist.
                If it&apos;s useful to you, chip in through any of these:
              </p>
            </Reveal>

            <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {siteConfig.supportLinks.map((link, i) => (
                <Reveal key={link.href} delay={i * 60}>
                  <a
                    href={link.href}
                    target="_blank"
                    rel="noreferrer"
                    className="group flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3.5 font-medium text-govnavy shadow-sm transition hover:-translate-y-0.5 hover:border-govblue hover:shadow-card"
                  >
                    <BrandIcon
                      name={link.icon}
                      className="h-6 w-6 shrink-0 text-slate-400 transition-colors group-hover:text-govblue"
                    />
                    <span>{link.label}</span>
                  </a>
                </Reveal>
              ))}
            </div>

            <Reveal className="mt-10">
              <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 sm:p-8">
                <h3 className="font-display font-semibold text-govnavy">
                  Seeking a fiscal sponsor
                </h3>
                <p className="mt-2 max-w-2xl text-sm text-slate-600">
                  GovMap is also looking for a fiscal sponsor — a 501(c)(3) or
                  civic-tech organization that can host a nonpartisan,
                  open-source government-transparency project. If that&apos;s you
                  (or someone you know), we&apos;d love to talk.
                </p>
                <a
                  href={siteConfig.githubUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-4 inline-block rounded-full bg-govnavy px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-govnavy/90"
                >
                  Get in touch on GitHub
                </a>
              </div>
            </Reveal>
          </div>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}
