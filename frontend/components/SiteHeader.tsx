"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { BugReport } from "@/components/BugReport";
import { HomeZipChip } from "@/components/HomeZipChip";
import { ThemeMenuChoice, ThemeToggle } from "@/components/ThemeControls";
import { UniversalSearch } from "@/components/UniversalSearch";
import { SECTIONS, type Section } from "@/lib/sections";
import { siteConfig } from "@/lib/site-config";
import { useScrollLock } from "@/lib/use-scroll-lock";

const APP_NAV = SECTIONS.filter((s) => s.group === "workspace" && s.availability === "live");
const PLANNED_NAV = SECTIONS.filter((s) => s.group === "workspace" && s.availability === "planned");
const PROJECT_NAV = SECTIONS.filter((s) => s.group === "project");

/** The live section the URL belongs to. The most specific match wins, so
 *  "/bills?status=became-law" highlights "Recently enacted laws", not "Bills". */
function activeSectionId(
  pathname: string,
  search: { get(name: string): string | null },
): string | null {
  let best: { id: string; score: number } | null = null;
  for (const s of SECTIONS) {
    if (s.availability !== "live") continue;
    const [path, query] = s.href.split("?");
    let score: number;
    if (query !== undefined) {
      let matches = pathname === path;
      new URLSearchParams(query).forEach((value, key) => {
        if (search.get(key) !== value) matches = false;
      });
      if (!matches) continue;
      score = path.length + 1000;
    } else if (path === "/" ? pathname === "/" : pathname === path || pathname.startsWith(`${path}/`)) {
      score = path.length;
    } else {
      continue;
    }
    if (!best || score > best.score) best = { id: s.id, score };
  }
  return best?.id ?? null;
}

function MenuIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6" aria-hidden="true">
      <path
        d="M4 6h16M4 12h16M4 18h16"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function NavLink({
  item,
  active,
  onClick,
}: {
  item: Section;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`rounded-md px-3 py-2 text-base font-medium transition-colors ${
        active ? "bg-white/10 text-white" : "text-white/70 hover:bg-white/5 hover:text-white"
      }`}
    >
      {item.label}
    </Link>
  );
}

function SectionLinks({
  sections,
  activeId,
  onNavigate,
}: {
  sections: readonly Section[];
  activeId: string | null;
  onNavigate: () => void;
}) {
  return (
    <>
      {sections.map((item) => (
        <NavLink key={item.id} item={item} active={item.id === activeId} onClick={onNavigate} />
      ))}
    </>
  );
}

// Reads the query string, so it sits behind a Suspense boundary.
function ActiveSectionLinks({
  sections,
  onNavigate,
}: {
  sections: readonly Section[];
  onNavigate: () => void;
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  return (
    <SectionLinks
      sections={sections}
      activeId={activeSectionId(pathname, searchParams)}
      onNavigate={onNavigate}
    />
  );
}

function MenuSections({ sections, onNavigate }: { sections: readonly Section[]; onNavigate: () => void }) {
  return (
    <Suspense fallback={<SectionLinks sections={sections} activeId={null} onNavigate={onNavigate} />}>
      <ActiveSectionLinks sections={sections} onNavigate={onNavigate} />
    </Suspense>
  );
}

/**
 * The persistent app header, mounted once by the root layout so it survives
 * navigation. Equal side tracks keep the search on the viewport's true center
 * whatever the logo, ZIP chip or menu button widths are.
 */
export function SiteHeader() {
  const pathname = usePathname();
  // The menu belongs to the page it was opened on, so Back/Forward closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const menuOpen = openOn === pathname;
  const close = () => setOpenOn(null);
  useScrollLock(menuOpen);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenOn(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <header className="chrome fixed inset-x-0 top-0 z-50 border-b border-white/10 bg-govnavy/80 backdrop-blur-lg">
      <div className="flex w-full items-center justify-between gap-4 px-6 py-3.5 md:grid md:grid-cols-[minmax(12rem,1fr)_minmax(0,36rem)_minmax(12rem,1fr)]">
        <Link
          href={siteConfig.appUrl}
          className="shrink-0 justify-self-start"
          aria-label="GovMap.us home"
          onClick={close}
        >
          <Image
            src="/logo-dark-transparent.png"
            alt="GovMap.us"
            width={160}
            height={50}
            priority
            className="h-auto w-32 sm:w-40"
          />
        </Link>

        <div className="hidden md:block">
          <UniversalSearch className="w-full" shortcut />
        </div>

        <div className="flex shrink-0 items-center justify-end gap-3 justify-self-end">
          <div className="hidden sm:block">
            <HomeZipChip />
          </div>
          <ThemeToggle />
          <button
            type="button"
            className="shrink-0 text-white"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            onClick={() => setOpenOn(menuOpen ? null : pathname)}
          >
            {menuOpen ? <CloseIcon /> : <MenuIcon />}
          </button>
        </div>
      </div>

      {typeof document !== "undefined" &&
        createPortal(
          <>
            {/* Backdrop — always mounted so it fades; pointer-events off when
                closed so it never blocks the page underneath. */}
            <div
              className={`chrome fixed inset-0 z-[55] bg-govnavy/70 backdrop-blur-sm transition-opacity duration-300 ${
                menuOpen ? "opacity-100" : "pointer-events-none opacity-0"
              }`}
              onClick={close}
              aria-hidden={true}
            />
            {/* Right-side blade. Portaled to <body> so the header's backdrop-blur
                (a containing block for `fixed`) can't clip it; always mounted so
                the slide transition actually animates. */}
            <div
              className={`chrome fixed inset-y-0 right-0 z-[60] flex w-full max-w-[340px] transform flex-col border-l border-white/10 bg-govnavy/95 shadow-2xl transition-transform duration-300 ease-out ${
                menuOpen ? "translate-x-0" : "translate-x-full"
              }`}
              aria-hidden={!menuOpen}
              inert={!menuOpen}
            >
              <div className="flex items-center justify-between px-6 py-3.5">
                <span className="text-sm font-semibold uppercase tracking-wider text-white/50">
                  Menu
                </span>
                <button
                  type="button"
                  onClick={close}
                  aria-label="Close menu"
                  className="text-white transition-colors hover:text-white/70"
                >
                  <CloseIcon />
                </button>
              </div>
              <nav
                className="flex flex-1 flex-col gap-1 overflow-y-auto px-6 pb-6"
                aria-label="Primary"
              >
                {/* Search here only where the centered bar is hidden (mobile). */}
                <div className="mb-3 md:hidden">
                  <UniversalSearch onNavigate={close} />
                </div>
                <MenuSections sections={APP_NAV} onNavigate={close} />

                <div className="mt-4 border-t border-white/10 pt-4">
                  <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wider text-white/40">
                    In development
                  </p>
                  {PLANNED_NAV.map((s) => (
                    <Link
                      key={s.id}
                      href={s.href}
                      onClick={close}
                      className="flex items-center justify-between gap-3 rounded-md px-3 py-1.5 text-sm text-white/55 transition-colors hover:bg-white/5 hover:text-white/80"
                    >
                      <span>{s.label}</span>
                      <span className="shrink-0 rounded-full border border-white/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white/45">
                        Planned
                      </span>
                    </Link>
                  ))}
                </div>

                <div className="mt-4 space-y-1 border-t border-white/10 pt-4">
                  <Link
                    href="/account"
                    onClick={close}
                    className="block rounded-md px-3 py-2 text-base font-medium text-white/80 transition-colors hover:bg-white/5"
                  >
                    Sign In
                  </Link>
                  <BugReport
                    triggerClassName="block w-full rounded-md px-3 py-2 text-left text-base font-medium text-white/80 transition-colors hover:bg-white/5"
                    triggerLabel="Report a problem"
                  />
                </div>
                <div className="mt-4 border-t border-white/10 pt-4">
                  <ThemeMenuChoice />
                </div>
                {/* Home-area chip lives in the bar on desktop; surface it here
                    for mobile, where it's part of the app experience. */}
                <div className="mt-4 border-t border-white/10 pt-4 sm:hidden">
                  <HomeZipChip />
                </div>

                {/* Project links pinned to the bottom of the blade. */}
                <div className="mt-auto flex flex-col gap-1 border-t border-white/10 pt-4">
                  <MenuSections sections={PROJECT_NAV} onNavigate={close} />
                  <p className="px-3 pt-3 text-xs text-white/40">{siteConfig.tagline}</p>
                </div>
              </nav>
            </div>
          </>,
          document.body,
        )}
    </header>
  );
}
