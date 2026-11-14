import Link from "next/link";

import { LegalLayout } from "@/components/LegalLayout";
import { siteConfig } from "@/lib/site-config";

export const metadata = {
  title: "Privacy Policy",
  description: "How GovMap.us handles data — a nonprofit, nonpartisan civic tool.",
};

export default function PrivacyPage() {
  return (
    <LegalLayout title="Privacy Policy" updated="November 12, 2026">
      <p>
        GovMap.us is a nonprofit, nonpartisan civic tool. We built it to make
        public government data easier to understand — not to collect data about
        you. This page explains, in plain English, what we do and -do not- do
        with anyone&apos;s information, including yours.
      </p>

      <h2>What we collect:</h2>
      <p>
        Today GovMap is a public informational website with no user accounts.
        You can browse everything without giving us any personal information.
        We will never sell data, run advertising, or use any third-party
        analytics or tracking pixels. While part of our roadmap includes 
        user account information, it will be optional and data you store 
        with us will remain under your control, under aggressive security 
        practices and policies.
      </p>

      <h2>Server and network logs:</h2>
      <p>
        Like any website, our infrastructure processes standard request
        metadata — such as IP address and browser type — to serve pages, keep
        the site secure, and diagnose problems. Traffic reaches us through
        Cloudflare, whose processing is governed by their own privacy terms.
        This metadata we collect is transient and never used to build a profile 
        of you.  
      </p>

      <h2>Cookies</h2>
      <p>
        GovMap sets no non-essential or advertising cookies - and never will.
      </p>

      <h2>What is stored on your device:</h2>
      <p>
        Your home ZIP and last map view are saved in your browser&apos;s local
        storage. The map view contains its position, zoom, House or Senate
        selection, and selected district or state, so returning does not lose
        your place. This view state is not sent to our servers. Your ZIP is sent
        to our district-lookup service when you set or restore your home area.
      </p>
      <p>
        If you choose the Light or Dark theme, that choice is saved in local
        storage too and never leaves your browser. Choosing System in the menu
        removes it, and the site follows your device setting again.
      </p>
      <p>
        Reset on the map replaces the saved map view with the national House
        view; it does not clear your home ZIP. Clear your home area separately,
        or clear this site&apos;s browser storage to remove both. Navigation
        history also remembers member views and scroll positions within a tab.
      </p>

      <h2>Links to other services:</h2>
      <p>
        When you follow a link to a donation platform (Ko-fi, Buy Me a Coffee,
        or Liberapay, listed on our <Link href="/support">Support page</Link>),
        one of our social accounts, or our source repository, you leave GovMap
        and that service&apos;s own privacy policy applies.
      </p>

      <h2>Where our data comes from:</h2>
      <p>
        The government information GovMap displays comes from public, official
        sources, which we read on our servers and normalize into a consistent
        format. Our sourcing and methodology are published openly — see{" "}
        <Link href="/about">About</Link> and <Link href="/security">Security</Link>.
      </p>

      <h2>What changes when accounts arrive</h2>
      <p>
        We plan to add optional accounts and email digests in the future. When
        we do, this policy will be updated to describe exactly what we store
        (such as your email and saved representatives), how to export it, and
        how to delete your account and data entirely.
      </p>

      <h2>Children:</h2>
      <p>
        GovMap is a general-audience civic resource and is not directed at
        children under the age of13.
      </p>

      <h2>Contact</h2>
      <p>
        Questions about privacy?{" "}
        {siteConfig.contactEmail && (
          <>
            Email{" "}
            <a href={`mailto:${siteConfig.contactEmail}`}>{siteConfig.contactEmail}</a> or{" "}
          </>
        )}
        reach us through our{" "}
        <a href={siteConfig.githubUrl} target="_blank" rel="noreferrer">
          GitHub repository
        </a>
        . We&apos;ll post any material changes to this policy on this page with
        an updated date.
      </p>
    </LegalLayout>
  );
}
