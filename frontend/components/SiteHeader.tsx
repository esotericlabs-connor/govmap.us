"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";

import { siteConfig } from "@/lib/site-config";

type NavItem = { label: string; href: string; external?: boolean };

const MARKETING_NAV: NavItem[] = [
  { label: "About", href: "/#about" },
  { label: "Support", href: "/#support" },
  { label: "GitHub", href: siteConfig.githubUrl, external: true },
];

const APP_NAV: NavItem[] = [
  { label: "Home", href: "/" },
  { label: "Members", href: "/members" },
];

function MenuIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6" aria-hidden="true">
      <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
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

export function SiteHeader({
  variant = "marketing",
}: {
  variant?: "marketing" | "app";
}) {
  const nav = variant === "marketing" ? MARKETING_NAV : APP_NAV;
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // App pages have no hero, so the bar is glassy from the top; the marketing
  // header floats transparent over the hero until you scroll.
  const glass = variant === "app" || scrolled || open;

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-colors duration-300 ${
        glass
          ? "border-b border-white/10 bg-govnavy/80 backdrop-blur-md"
          : "border-b border-transparent bg-transparent"
      }`}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
        <Link
          href="/"
          className="shrink-0"
          aria-label="GovMap.us home"
          onClick={() => setOpen(false)}
        >
          <Image
            src="/logo-dark-transparent.png"
            alt="GovMap.us"
            width={168}
            height={54}
            priority
          />
        </Link>

        <nav className="hidden items-center gap-8 md:flex" aria-label="Primary">
          {nav.map((item) => (
            <a
              key={item.label}
              href={item.href}
              {...(item.external ? { target: "_blank", rel: "noreferrer" } : {})}
              className="text-sm font-medium text-white/75 transition-colors hover:text-white"
            >
              {item.label}
            </a>
          ))}
          <a
            href="/account"
            className="text-sm font-medium text-white/75 transition-colors hover:text-white"
          >
            Sign in
          </a>
          <a
            href={siteConfig.appUrl}
            className="rounded-full bg-white px-5 py-2 text-sm font-semibold text-govnavy transition hover:bg-white/90"
          >
            Enter GovMap
          </a>
        </nav>

        <button
          type="button"
          className="text-white md:hidden"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <CloseIcon /> : <MenuIcon />}
        </button>
      </div>

      {open && (
        <div className="border-t border-white/10 bg-govnavy/95 backdrop-blur-md md:hidden">
          <nav className="mx-auto flex max-w-6xl flex-col gap-1 px-6 py-4" aria-label="Mobile">
            {nav.map((item) => (
              <a
                key={item.label}
                href={item.href}
                {...(item.external ? { target: "_blank", rel: "noreferrer" } : {})}
                onClick={() => setOpen(false)}
                className="rounded-md px-2 py-3 text-base font-medium text-white/80 transition-colors hover:bg-white/5 hover:text-white"
              >
                {item.label}
              </a>
            ))}
            <a
              href="/account"
              onClick={() => setOpen(false)}
              className="rounded-md px-2 py-3 text-base font-medium text-white/80 transition-colors hover:bg-white/5 hover:text-white"
            >
              Sign in
            </a>
            <a
              href={siteConfig.appUrl}
              onClick={() => setOpen(false)}
              className="mt-2 rounded-full bg-white px-5 py-3 text-center text-base font-semibold text-govnavy"
            >
              Enter GovMap
            </a>
          </nav>
        </div>
      )}
    </header>
  );
}
