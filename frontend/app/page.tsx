import Image from "next/image";

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
    <svg
      viewBox="0 0 20 20"
      fill="none"
      className="h-5 w-5 shrink-0 text-govblue"
      aria-hidden="true"
    >
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
    <main>
      {/* Hero */}
      <section className="bg-govnavy">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
          <Image src="/logo-dark.png" alt="GovMap.us" width={130} height={73} priority />
          <nav className="hidden items-center gap-8 text-sm font-medium text-white/70 sm:flex">
            <a href="#about" className="transition-colors hover:text-white">
              About
            </a>
            <a href="#support" className="transition-colors hover:text-white">
              Support
            </a>
            <a
              href={siteConfig.githubUrl}
              className="transition-colors hover:text-white"
              target="_blank"
              rel="noreferrer"
            >
              GitHub
            </a>
          </nav>
          <a
            href={siteConfig.appUrl}
            className="rounded-md bg-white px-4 py-2 text-sm font-semibold text-govnavy transition-colors hover:bg-white/90"
          >
            Enter GovMap
          </a>
        </div>

        <div className="mx-auto flex max-w-6xl flex-col items-start gap-6 px-6 pb-28 pt-12 sm:pt-20">
          <h1 className="max-w-2xl text-4xl font-bold leading-tight text-white sm:text-5xl">
            See your government. Clearly.
          </h1>
          <p className="max-w-xl text-lg text-white/70">
            GovMap is a nonpartisan, plain-English view of the entire US federal
            government — who represents you, how they vote, who runs the
            agencies that govern you, where the money goes, and how a bill
            becomes law. Real data, always sourced. No spin.
          </p>
          <div className="flex flex-wrap gap-4 pt-2">
            <a
              href={siteConfig.appUrl}
              className="rounded-md bg-govblue px-6 py-3 font-semibold text-govnavy transition-colors hover:bg-govblue/90"
            >
              Enter GovMap →
            </a>
            <a
              href="#about"
              className="rounded-md border border-white/25 px-6 py-3 font-semibold text-white transition-colors hover:border-white/50"
            >
              How it works
            </a>
          </div>
        </div>
      </section>

      {/* About */}
      <section id="about" className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="text-3xl font-bold text-govnavy">
          One nonpartisan view of all three branches
        </h2>
        <p className="mt-4 max-w-2xl text-slate-600">
          Most civic tools stop at Congress. GovMap treats the Legislative,
          Executive, and Judicial branches as equal pillars — and connects
          them: a bill&apos;s full journey from introduction, through signature
          or veto, through any judicial challenge, in a single timeline. No
          other civic tool currently shows all three stages in one view.
        </p>

        <div className="mt-10 grid gap-6 sm:grid-cols-3">
          {BRANCHES.map((branch) => (
            <div
              key={branch.name}
              className="rounded-lg border border-slate-200 p-6"
            >
              <h3 className="font-semibold text-govnavy">{branch.name}</h3>
              <p className="mt-2 text-sm text-slate-600">{branch.covers}</p>
              <p className="mt-4 text-xs font-medium uppercase tracking-wide text-govblue">
                {branch.cadence}
              </p>
            </div>
          ))}
        </div>

        <div className="mt-14 rounded-lg bg-slate-50 p-8">
          <h3 className="font-semibold text-govnavy">
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
      </section>

      {/* Support */}
      <section id="support" className="bg-slate-50">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="text-3xl font-bold text-govnavy">Support GovMap</h2>
          <p className="mt-4 max-w-2xl text-slate-600">
            GovMap is a nonprofit, nonpartisan civic tool — no advertising, no
            political funding. It runs on donations, civic grants, and the
            time of the people who believe transparent government tooling
            should exist. Sustainability comes from credibility and organic
            reach, not ad revenue.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            {siteConfig.supportUrl ? (
              <a
                href={siteConfig.supportUrl}
                className="rounded-md bg-govnavy px-6 py-3 font-semibold text-white transition-colors hover:bg-govnavy/90"
              >
                Support GovMap
              </a>
            ) : (
              <p className="rounded-md border border-dashed border-slate-300 px-6 py-3 text-sm text-slate-500">
                Support options are coming soon — GovMap is currently
                self-funded during early development.
              </p>
            )}
            <a
              href={siteConfig.githubUrl}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-slate-300 px-6 py-3 font-semibold text-govnavy transition-colors hover:border-slate-400"
            >
              Follow the build on GitHub
            </a>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-govnavy">
        <div className="mx-auto max-w-6xl px-6 py-14">
          <Image src="/logo-dark.png" alt="GovMap.us" width={110} height={62} />
          <p className="mt-3 text-sm text-white/50">{siteConfig.tagline}</p>

          <div className="mt-8 flex flex-wrap gap-6 text-sm text-white/70">
            <a href={siteConfig.appUrl} className="hover:text-white">
              Enter GovMap
            </a>
            <a
              href={siteConfig.githubUrl}
              target="_blank"
              rel="noreferrer"
              className="hover:text-white"
            >
              GitHub
            </a>
            {siteConfig.contactEmail && (
              <a href={`mailto:${siteConfig.contactEmail}`} className="hover:text-white">
                Contact
              </a>
            )}
            {siteConfig.socialLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                target="_blank"
                rel="noreferrer"
                className="hover:text-white"
              >
                {link.label}
              </a>
            ))}
          </div>

          <p className="mt-10 text-xs text-white/40">
            © {new Date().getFullYear()} GovMap.us — a nonprofit, nonpartisan
            civic project. Data only, always sourced.
          </p>
        </div>
      </footer>
    </main>
  );
}
