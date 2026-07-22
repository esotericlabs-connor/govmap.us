import { LegalLayout } from "@/components/LegalLayout";
import { siteConfig } from "@/lib/site-config";

export const metadata = {
  title: "Security",
  description: "How to responsibly report a security issue in GovMap.us.",
};

export default function SecurityPage() {
  return (
    <LegalLayout title="Security" updated="July 22, 2026">
      <p>
        We take the integrity of GovMap seriously — a civic tool is only useful
        if people can trust it. If you believe you&apos;ve found a security
        vulnerability, we&apos;d genuinely appreciate your help in disclosing it
        responsibly.
      </p>

      <h2>Reporting a vulnerability</h2>
      <p>
        Please report suspected vulnerabilities privately through a{" "}
        <a
          href={`${siteConfig.githubUrl}/security/advisories/new`}
          target="_blank"
          rel="noreferrer"
        >
          GitHub security advisory
        </a>{" "}
        on our repository. Do not open a public issue or pull request for a
        security bug, and please don&apos;t disclose it publicly until we&apos;ve
        had a reasonable chance to fix it.
      </p>

      <h2>Scope</h2>
      <ul>
        <li>The GovMap website (govmap.us) and API (api.govmap.us)</li>
        <li>The open-source codebase in our repository</li>
      </ul>

      <h2>Good-faith safe harbor</h2>
      <p>
        We will not pursue or support legal action against security research
        conducted in good faith that respects user privacy, avoids destroying or
        degrading data and service, stays within the scope above, and gives us
        reasonable time to respond before public disclosure.
      </p>

      <h2>Please avoid</h2>
      <ul>
        <li>Denial-of-service testing or anything that degrades the service</li>
        <li>Accessing, modifying, or deleting data that isn&apos;t yours</li>
        <li>Social engineering of maintainers, users, or infrastructure providers</li>
      </ul>

      <h2>Our commitment</h2>
      <p>
        We&apos;ll acknowledge valid reports, keep you updated as we work on a
        fix, and — with your permission — credit you once it&apos;s resolved.
      </p>

      <h2>How the site is run</h2>
      <p>
        For context: GovMap runs behind Cloudflare with no publicly exposed
        inbound ports (traffic arrives through an outbound tunnel), secrets live
        only in environment variables outside the codebase, and the full stack
        is open source and auditable.
      </p>
    </LegalLayout>
  );
}
