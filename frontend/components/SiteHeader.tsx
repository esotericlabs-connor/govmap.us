"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { AppSettings } from "@/components/AppSettings";
import { HomeZipChip } from "@/components/HomeZipChip";
import { UniversalSearch } from "@/components/UniversalSearch";
import { activeSectionId, NAVIGATION_GROUPS, SECTIONS, type Section } from "@/lib/sections";
import { siteConfig } from "@/lib/site-config";
import { useScrollLock } from "@/lib/use-scroll-lock";

const PLANNED_NAV = SECTIONS.filter((s) => s.group === "workspace" && s.availability === "planned");

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
      className={`block rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
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
  const [openOn, setOpenOn] = useState<{ pathname: string; panel: "navigation" | "settings" } | null>(null);
  const menuOpen = openOn?.pathname === pathname && openOn.panel === "navigation";
  const settingsOpen = openOn?.pathname === pathname && openOn.panel === "settings";
  const close = useCallback(() => setOpenOn(null), []);
  const dialogRef = useRef<HTMLDialogElement>(null);
  useScrollLock(menuOpen);

  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (menuOpen && !dialog.open) dialog.showModal();
    else if (!menuOpen && dialog.open) dialog.close();
  }, [menuOpen]);

  useEffect(() => {
    window.addEventListener("popstate", close);
    return () => window.removeEventListener("popstate", close);
  }, [close]);

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-slate-warm-200 bg-white">
      <div className="flex w-full items-center justify-between gap-4 px-6 py-3.5 md:grid md:grid-cols-[minmax(12rem,1fr)_minmax(0,32rem)_minmax(12rem,1fr)]">
        <Link
          href={siteConfig.appUrl}
          className="relative block h-[41px] w-32 shrink-0 justify-self-start sm:h-[51px] sm:w-40"
          aria-label="GovMap.us home"
          onClick={close}
        >
          <Image
            src="/logo-light.png"
            alt="GovMap.us"
            fill
            sizes="160px"
            className="object-contain object-left dark:hidden"
          />
          <Image
            src="/logo-dark-transparent.png"
            alt="GovMap.us"
            fill
            sizes="160px"
            className="hidden object-contain object-left dark:block"
          />
        </Link>

        <div className="hidden md:block">
          <UniversalSearch className="w-full" shortcut />
        </div>

        <div className="flex shrink-0 items-center justify-end gap-3 justify-self-end">
          <div className="hidden sm:block">
            <HomeZipChip />
          </div>
          <AppSettings
            open={settingsOpen}
            onToggle={() => setOpenOn(settingsOpen ? null : { pathname, panel: "settings" })}
            onClose={close}
          />
          <button
            type="button"
            className="shrink-0 text-govnavy"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            aria-controls="app-navigation"
            aria-haspopup="dialog"
            onClick={() => setOpenOn(menuOpen ? null : { pathname, panel: "navigation" })}
          >
            {menuOpen ? <CloseIcon /> : <MenuIcon />}
          </button>
        </div>
      </div>

      {typeof document !== "undefined" &&
        createPortal(
            <dialog
              ref={dialogRef}
              id="app-navigation"
              aria-labelledby="app-navigation-title"
              aria-modal="true"
              onCancel={(event) => {
                event.preventDefault();
                close();
              }}
              onClick={(event) => {
                if (event.target !== event.currentTarget) return;
                const bounds = event.currentTarget.getBoundingClientRect();
                if (event.clientX < bounds.left || event.clientX > bounds.right) close();
              }}
              className="navigation-dialog chrome fixed inset-y-0 left-auto right-0 m-0 h-dvh max-h-none w-full max-w-2xl overflow-hidden border-l border-white/10 bg-govnavy p-0 text-white shadow-2xl backdrop:bg-govnavy/70 backdrop:backdrop-blur-sm"
            >
            <div className="flex h-full flex-col">
              <div className="flex items-center justify-between border-b border-white/10 px-6 py-5">
                <div>
                  <h2 id="app-navigation-title" className="font-display text-xl font-bold">Explore GovMap</h2>
                  <p className="mt-1 text-xs text-white/50">Your government, organized.</p>
                </div>
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
                className="flex-1 overflow-y-auto overscroll-contain px-5 py-5"
                aria-label="Primary"
              >
                {/* Search here only where the centered bar is hidden (mobile). */}
                <div className="mb-3 md:hidden">
                  <UniversalSearch tone="chrome" onNavigate={close} />
                </div>
                <div className="grid gap-6 sm:grid-cols-2">
                  {NAVIGATION_GROUPS.map((group) => (
                    <section key={group.id} aria-labelledby={`navigation-${group.id}`}>
                      <h3 id={`navigation-${group.id}`} className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-govblue-400">
                        {group.label}
                      </h3>
                      <MenuSections
                        sections={SECTIONS.filter((section) => section.navigationGroup === group.id && section.availability === "live")}
                        onNavigate={close}
                      />
                    </section>
                  ))}
                </div>

                <details className="mt-6 border-t border-white/10 pt-4">
                  <summary className="cursor-pointer rounded-lg px-3 py-2 text-xs font-semibold uppercase tracking-wider text-white/50 hover:text-white">
                    Coming next
                  </summary>
                  <div className="mt-2 grid gap-1 sm:grid-cols-2">
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
                </details>
              </nav>
              <div className="border-t border-white/10 px-8 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
                <p className="text-xs text-white/50">{siteConfig.tagline}</p>
                <p className="mt-1 text-[11px] text-white/40">Theme, home area and feedback are in Settings in the header.</p>
              </div>
            </div>
            </dialog>,
          document.body,
        )}
    </header>
  );
}
