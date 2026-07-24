"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { UniversalSearch } from "@/components/UniversalSearch";
import { siteConfig } from "@/lib/site-config";

type NavItem = { label: string; href: string; external?: boolean };

const MARKETING_NAV: NavItem[] = [
  { label: "About", href: "/#about" },
  { label: "Support", href: "/#support" },
  { label: "GitHub", href: siteConfig.githubUrl, external: true },
];

const APP_NAV: NavItem[] = [
  { label: "Congress", href: "/congress" },
  { label: "Members", href: "/members" },
  { label: "Bills", href: "/bills" },
  { label: "Votes", href: "/votes" },
];

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
  isMobile,
  onClick,
}: {
  item: NavItem;
  active: boolean;
  isMobile?: boolean;
  onClick?: () => void;
}) {
  return (
    <Link
      href={item.href}
      {...(item.external ? { target: "_blank", rel: "noreferrer" } : {})}
      onClick={onClick}
      className={`relative transition-colors ${
        isMobile
          ? "rounded-md px-3 py-2 text-base font-medium"
          : "text-sm font-medium"
      } ${
        active
          ? "text-white"
          : "text-white/70 hover:text-white"
      }`}
    >
      {item.label}
      {active && !isMobile && (
        <span className="absolute -bottom-2 left-1/2 h-0.5 w-4 -translate-x-1/2 rounded-full bg-govblue" />
      )}
    </Link>
  );
}

export function SiteHeader({
  variant = "marketing",
}: {
  variant?: "marketing" | "app";
}) {
  const navItems = variant === "marketing" ? MARKETING_NAV : APP_NAV;
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 10);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

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

  // App pages have no hero, so the bar is glassy from the top; the marketing
  // header floats transparent over the hero until you scroll.
  const isGlassy = variant === "app" || scrolled || menuOpen;

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${
        isGlassy
          ? "border-b border-white/10 bg-govnavy/80 backdrop-blur-lg"
          : "border-b border-transparent bg-transparent"
      }`}
    >
      <div className="flex w-full items-center justify-between gap-4 px-6 py-3.5">
        <Link
          href="/"
          className="shrink-0"
          aria-label="GovMap.us home"
          onClick={() => setMenuOpen(false)}
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

        {/* Universal search — centered on app pages */}
        {variant === "app" && (
          <div className="hidden flex-1 justify-center px-4 md:flex">
            <UniversalSearch className="w-full max-w-md" />
          </div>
        )}

        {/* Desktop Nav */}
        <nav className="hidden items-center gap-8 md:flex" aria-label="Primary">
          {navItems.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              active={pathname.startsWith(item.href)}
            />
          ))}
        </nav>

        <div className="hidden shrink-0 items-center gap-4 md:flex">
          {variant === "marketing" && (
            <Link
              href={siteConfig.appUrl}
              className="transform rounded-full bg-white px-5 py-2 text-sm font-semibold text-govnavy shadow-md transition-transform duration-200 hover:-translate-y-0.5 active:translate-y-0"
            >
              Enter App
            </Link>
          )}
          {variant === "app" && (
            <Link
              href="/account"
              className="text-sm font-medium text-white/70 transition-colors hover:text-white"
            >
              Sign In
            </Link>
          )}
        </div>

        {/* Mobile Menu Button */}
        <button
          type="button"
          className="text-white md:hidden"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((v) => !v)}
        >
          {menuOpen ? <CloseIcon /> : <MenuIcon />}
        </button>
      </div>

      {/* Mobile Menu */}
      {menuOpen && (
        <div className="border-t border-white/10 bg-govnavy/95 backdrop-blur-lg md:hidden">
          <nav
            className="mx-auto flex max-w-6xl flex-col gap-1 px-6 pb-6 pt-4"
            aria-label="Mobile"
          >
            {variant === "app" && (
              <div className="mb-3">
                <UniversalSearch onNavigate={() => setMenuOpen(false)} />
              </div>
            )}
            {navItems.map((item) => (
              <NavLink
                key={item.href}
                item={item}
                active={pathname.startsWith(item.href)}
                isMobile
                onClick={() => setMenuOpen(false)}
              />
            ))}
            <div className="mt-4 border-t border-white/10 pt-4">
              {variant === "marketing" ? (
                <Link
                  href={siteConfig.appUrl}
                  onClick={() => setMenuOpen(false)}
                  className="block w-full rounded-full bg-govblue px-5 py-3 text-center text-base font-semibold text-govnavy shadow-lg"
                >
                  Enter GovMap App
                </Link>
              ) : (
                <Link
                  href="/account"
                  onClick={() => setMenuOpen(false)}
                  className="block rounded-md px-3 py-2 text-base font-medium text-white/80 transition-colors hover:bg-white/5"
                >
                  Sign In
                </Link>
              )}
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
