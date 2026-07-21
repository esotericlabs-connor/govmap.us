import Image from "next/image";
import Link from "next/link";
import type { Metadata } from "next";

import { siteConfig } from "@/lib/site-config";

export const metadata: Metadata = {
  title: "GovMap",
  description: "Members of Congress, plain and sourced.",
};

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between gap-4 bg-govnavy px-6 py-3">
        <Link href="/" className="shrink-0">
          <Image
            src="/logo-dark.png"
            alt="GovMap.us"
            width={140}
            height={79}
            priority
          />
        </Link>
        <nav className="flex items-center gap-6 text-sm font-medium text-white/80">
          <Link href="/" className="transition-colors hover:text-white">
            Home
          </Link>
          <Link href="/members" className="transition-colors hover:text-white">
            Members of Congress
          </Link>
          <a
            href={siteConfig.marketingUrl}
            className="rounded-md border border-white/20 px-3 py-1.5 text-white/70 transition-colors hover:border-white/40 hover:text-white"
          >
            ← govmap.us
          </a>
        </nav>
      </header>
      <div className="flex-1 bg-white">{children}</div>
    </div>
  );
}
