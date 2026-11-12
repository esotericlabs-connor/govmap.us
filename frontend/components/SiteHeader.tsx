"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { BugReport } from "@/components/BugReport";
import { HomeZipChip } from "@/components/HomeZipChip";
import { UniversalSearch } from "@/components/UniversalSearch";
import { siteConfig } from "@/lib/site-config";

type NavItem = { label: string; href: string };

const APP_NAV: NavItem[] = [
  { label: "Map", href: "/" },
  { label: "Members", href: "/members" },
  { label: "Bills", href: "/bills" },
  { label: "Votes", href: "/votes" },
];

const PROJECT_NAV: NavItem[] = [
  { label: "About GovMap", href: "/about" },
  { label: "Support the project", href: "/support" },
];

// "/" would prefix-match every route, so the map is active only on itself.
function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
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
  item: NavItem;
  active: boolean;
  onClick?: () => void;
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

export function SiteHeader() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const close = () => setMenuOpen(false);

  useEffect(() => {
    if (menuOpen) document.body.style.overflow = "hidden";
    else document.body.style.overflow = "";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-white/10 bg-govnavy/80 backdrop-blur-lg">
      <div className="relative flex w-full items-center justify-between gap-4 px-6 py-3.5">
        <Link
          href={siteConfig.appUrl}
          className="shrink-0"
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

        {/* Universal search — prominent and centered on desktop. */}
        <div className="hidden flex-1 justify-center px-4 md:flex">
          <UniversalSearch className="w-full max-w-xl" />
        </div>

        <div className="hidden shrink-0 sm:block">
          <HomeZipChip />
        </div>

        <button
          type="button"
          className="shrink-0 text-white"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((v) => !v)}
        >
          {menuOpen ? <CloseIcon /> : <MenuIcon />}
        </button>
      </div>

      {typeof document !== "undefined" &&
        createPortal(
          <>
            {/* Backdrop — always mounted so it fades; pointer-events off when
                closed so it never blocks the page underneath. */}
            <div
              className={`fixed inset-0 z-[55] bg-govnavy/70 backdrop-blur-sm transition-opacity duration-300 ${
                menuOpen ? "opacity-100" : "pointer-events-none opacity-0"
              }`}
              onClick={close}
              aria-hidden={true}
            />
            {/* Right-side blade. Portaled to <body> so the header's backdrop-blur
                (a containing block for `fixed`) can't clip it; always mounted so
                the slide transition actually animates. */}
            <div
              className={`fixed inset-y-0 right-0 z-[60] flex w-full max-w-[340px] transform flex-col border-l border-white/10 bg-govnavy/95 shadow-2xl transition-transform duration-300 ease-out ${
                menuOpen ? "translate-x-0" : "translate-x-full"
              }`}
              aria-hidden={!menuOpen}
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
                {APP_NAV.map((item) => (
                  <NavLink
                    key={item.href}
                    item={item}
                    active={isActive(pathname, item.href)}
                    onClick={close}
                  />
                ))}
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
                {/* Home-area chip lives in the bar on desktop; surface it here
                    for mobile, where it's part of the app experience. */}
                <div className="mt-4 border-t border-white/10 pt-4 sm:hidden">
                  <HomeZipChip />
                </div>

                {/* Project links pinned to the bottom of the blade. */}
                <div className="mt-auto flex flex-col gap-1 border-t border-white/10 pt-4">
                  {PROJECT_NAV.map((item) => (
                    <NavLink
                      key={item.href}
                      item={item}
                      active={isActive(pathname, item.href)}
                      onClick={close}
                    />
                  ))}
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
