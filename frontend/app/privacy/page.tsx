import { LegalLayout } from "@/components/LegalLayout";
import { siteConfig } from "@/lib/site-config";

export const metadata = {
  title: "Privacy Policy",
  description: "How GovMap.us handles data — a nonprofit, nonpartisan civic tool.",
};

export default function PrivacyPage() {
  return (
    <LegalLayout title="Privacy Policy" updated="July 22, 2026">
      <p>
        GovMap.us is a nonprofit, nonpartisan civic tool. We built it to make
        public government data easier to understand — not to collect data about
        you. This page explains, in plain English, what we do and don&apos;t do
        with information.
      </p>

      <h2>What we collect</h2>
      <p>
        Today GovMap is a public informational website with no user accounts.
        You can browse everything without giving us any personal information. We
        do not sell data, we run no advertising, and we use no third-party
        analytics or tracking pixels.
      </p>

      <h2>Server and network logs</h2>
      <p>
        Like any website, our infrastructure processes standard request
        metadata — such as IP address and browser type — to serve pages, keep
        the site secure, and diagnose problems. Traffic reaches us through
        Cloudflare, whose processing is governed by their own privacy terms.
        This metadata is transient and is not used to build a profile of you.
      </p>

      <h2>Cookies</h2>
      <p>
        GovMap sets no non-essential or advertising cookies. If that ever
        changes, we will describe it here first.
      </p>

      <h2>Links to other services</h2>
      <p>
        When you follow a link to a donation platform (Patreon, Ko-fi, Open
        Collective, and the others on our Support page), a social account, or
        our source repository, you leave GovMap and that service&apos;s own
        privacy policy applies.
      </p>

      <h2>Where our data comes from</h2>
      <p>
        The government information GovMap displays comes from public, official
        sources, which we read on our servers and normalize into a consistent
        format. Our sourcing and methodology are published openly.
      </p>

      <h2>What changes when accounts arrive</h2>
      <p>
        We plan to add optional accounts and email digests in the future. When
        we do, this policy will be updated to describe exactly what we store
        (such as your email and saved representatives), how to export it, and
        how to delete your account and data entirely.
      </p>

      <h2>Children</h2>
      <p>
        GovMap is a general-audience civic resource and is not directed at
        children under 13.
      </p>

      <h2>Contact</h2>
      <p>
        Questions about privacy? Reach us through our{" "}
        <a href={siteConfig.githubUrl} target="_blank" rel="noreferrer">
          GitHub repository
        </a>
        . We&apos;ll post any material changes to this policy on this page with
        an updated date.
      </p>
    </LegalLayout>
  );
}
