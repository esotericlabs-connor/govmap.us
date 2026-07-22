import type { ReactNode } from "react";

import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

export function LegalLayout({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: ReactNode;
}) {
  return (
    <>
      <SiteHeader variant="app" />
      <main className="min-h-screen bg-white pb-20 pt-24">
        <article className="mx-auto max-w-3xl px-6 py-10">
          <div className="mb-8 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <strong className="font-semibold">Draft.</strong> This is a placeholder
            pending review — not yet a final policy.
          </div>
          <h1 className="font-display text-4xl font-bold text-govnavy">{title}</h1>
          <p className="mt-2 text-sm text-slate-500">Last updated: {updated}</p>
          <div className="legal-prose mt-8">{children}</div>
        </article>
      </main>
      <SiteFooter />
    </>
  );
}
