import Image from "next/image";
import type { ReactNode } from "react";

/**
 * The GovMap visual signature: the Capitol photo under a navy scrim with white
 * text. Shared by the footer and every page banner so the look stays identical.
 * Place inside a `relative isolate overflow-hidden` container.
 */
export function CapitolBackdrop({
  position = "bottom",
  priority = false,
}: {
  position?: "bottom" | "center";
  priority?: boolean;
}) {
  return (
    <>
      <Image
        src="/capitol-hero.jpg"
        alt=""
        fill
        sizes="100vw"
        priority={priority}
        className={`-z-10 object-cover ${position === "center" ? "object-center" : "object-bottom"}`}
      />
      <div className="absolute inset-0 -z-10 bg-govnavy/70" aria-hidden="true" />
    </>
  );
}

export function PageBanner({
  eyebrow,
  title,
  children,
}: {
  eyebrow?: string;
  title: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section className="relative isolate overflow-hidden bg-govnavy-800 text-white">
      <CapitolBackdrop position="center" priority />
      <div className="mx-auto max-w-6xl px-6 pb-14 pt-32 sm:pb-20 sm:pt-40">
        {eyebrow && (
          <p className="text-sm font-semibold uppercase tracking-wider text-white/60">{eyebrow}</p>
        )}
        <h1 className="mt-3 max-w-3xl font-display text-4xl font-bold tracking-tight sm:text-5xl">
          {title}
        </h1>
        {children && <div className="mt-5 max-w-2xl text-lg leading-relaxed text-white/80">{children}</div>}
      </div>
    </section>
  );
}

/** A white-on-navy card for content laid over or beside the banner look. */
export function BannerCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`relative isolate overflow-hidden rounded-2xl bg-govnavy-800 p-6 text-white shadow-card sm:p-8 ${className}`}
    >
      <CapitolBackdrop />
      {children}
    </div>
  );
}
