import type { ReactNode } from "react";

import { PageBanner } from "@/components/PageBanner";
import { SiteFooter } from "@/components/SiteFooter";

export function LegalLayout({
  title,
  updated,
  lede,
  children,
}: {
  title: string;
  updated: string;
  lede?: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      <main className="min-h-screen bg-white">
        <PageBanner eyebrow={`Last updated ${updated}`} title={title}>
          {lede}
        </PageBanner>
        <article className="mx-auto max-w-3xl px-6 pb-20 pt-10">
          <div className="mb-8 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <strong className="font-semibold">Draft.</strong> This is a placeholder
            pending review — not yet a final policy.
          </div>
          <div className="legal-prose">{children}</div>
        </article>
      </main>
      <SiteFooter />
    </>
  );
}
