import Link from "next/link";

import { LegalLayout } from "@/components/LegalLayout";
import { siteConfig } from "@/lib/site-config";

export const metadata = {
  title: "Security & Transparency",
  description:
    "How GovMap.us stays open, transparent and secure — open-source code, public data only, and how to report a vulnerability.",
};

export default function SecurityPage() {
  const repo = siteConfig.githubUrl;
  return (
    <LegalLayout
      title="Security & Transparency"
      updated="November 12, 2026"
      lede={
        <p>
          A civic tool is only useful if people can trust it. GovMap earns that
          trust by working in the open: open-source code, public data only, and
          every fact traced back to its official source.
        </p>
      }
    >
      <h2>Open source, top to bottom</h2>
      <p>
        Every line of GovMap — the website, the data pipelines, the database
        schema and the deployment setup — is public on{" "}
        <a href={repo} target="_blank" rel="noreferrer">
          GitHub
        </a>{" "}
        under the GPLv3 license. You don&apos;t have to take our word for how the
        data is gathered or displayed; you can read the code that does it.
      </p>
      <ul>
        <li>
          Every change runs through automated checks before release: linting,
          type-checking, tests, database migration checks, dependency
          vulnerability audits and container image scans.
        </li>
        <li>
          Dependencies are pinned to exact versions and updated deliberately
          through reviewed weekly updates, never silently.
        </li>
        <li>
          Changes are tested on a separate development site before they reach
          govmap.us.
        </li>
      </ul>

      <h2>Transparency in what we publish</h2>
      <ul>
        <li>
          <strong>Sourced, not written.</strong> GovMap shows official records —
          it doesn&apos;t editorialize. Records link back to the government
          source they came from so you can verify them.
        </li>
        <li>
          <strong>No AI-generated content.</strong> Bill summaries are the
          official summaries written by the Congressional Research Service. We
          don&apos;t generate, rewrite or score anything with AI.
        </li>
        <li>
          <strong>Honest about coverage.</strong> We say plainly what&apos;s live
          and what&apos;s still planned — see{" "}
          <Link href="/about">About GovMap</Link>.
        </li>
        <li>
          <strong>Independent funding.</strong> No advertising and no political
          money. GovMap is funded by small donations — see{" "}
          <Link href="/support">Support</Link>.
        </li>
      </ul>

      <h2>Public data only</h2>
      <p>
        Everything GovMap displays is already public: government records from
        sources like Congress.gov, the House Clerk, the U.S. Senate and the
        Federal Election Commission. We collect that public data on our own
        servers and present it — we don&apos;t gather data about you to do it.
      </p>
      <p>
        There are no user accounts, no advertising and no tracking pixels today.
        If you enter a ZIP code, it&apos;s used only to look up your districts and
        is remembered in your own browser, not in an account. Read the{" "}
        <Link href="/privacy">Privacy Policy</Link> for the full details.
      </p>

      <h2>How the site is protected</h2>
      <ul>
        <li>
          No open doors: the servers accept no direct inbound connections.
          Visitors reach GovMap only through Cloudflare&apos;s encrypted tunnel,
          and the database is never exposed to the internet.
        </li>
        <li>
          Secrets such as API keys and passwords live only in the server
          environment — never in the code or its history.
        </li>
        <li>
          Strict browser security headers, HTTPS everywhere, and every request
          checked against a defined shape before it reaches the database.
        </li>
        <li>
          Internal tools are locked behind credentials, and the development site
          is behind access control.
        </li>
        <li>
          The database is backed up daily, with continuous change logs for
          point-in-time recovery and copies kept off-site. Restores are tested,
          not assumed.
        </li>
      </ul>

      <h2>Reporting a vulnerability</h2>
      <p>
        If you believe you&apos;ve found a security issue, please report it
        privately through a{" "}
        <a href={`${repo}/security/advisories/new`} target="_blank" rel="noreferrer">
          GitHub security advisory
        </a>
        {siteConfig.contactEmail && (
          <>
            {" "}
            or by email to{" "}
            <a href={`mailto:${siteConfig.contactEmail}`}>{siteConfig.contactEmail}</a>
          </>
        )}
        . Please don&apos;t open a public issue for a security bug, and give us a
        reasonable chance to fix it before disclosing it publicly.
      </p>

      <h3>Scope</h3>
      <ul>
        <li>The GovMap website and its API at govmap.us</li>
        <li>The open-source code in our repository</li>
      </ul>

      <h3>Please avoid</h3>
      <ul>
        <li>Denial-of-service testing or anything that degrades the service</li>
        <li>Accessing, modifying or deleting data that isn&apos;t yours</li>
        <li>Social engineering of maintainers, users or infrastructure providers</li>
      </ul>

      <h3>Good-faith safe harbor</h3>
      <p>
        We will not pursue or support legal action against security research
        conducted in good faith that respects user privacy, avoids destroying or
        degrading data and service, stays within the scope above, and gives us
        reasonable time to respond before public disclosure.
      </p>

      <h3>Our commitment</h3>
      <p>
        We&apos;ll acknowledge valid reports, keep you updated as we work on a
        fix, and — with your permission — credit you once it&apos;s resolved.
      </p>
    </LegalLayout>
  );
}
