"use client";

import { useEffect, useState, type ReactNode } from "react";

function MoonIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5" aria-hidden="true">
      <path d="M17.5 12.9A7.5 7.5 0 017.1 2.5a7.5 7.5 0 1010.4 10.4z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      className="h-5 w-5"
      aria-hidden="true"
    >
      <circle cx="10" cy="10" r="3.4" />
      <path d="M10 1.8v2M10 16.2v2M1.8 10h2M16.2 10h2M4.4 4.4l1.4 1.4M14.2 14.2l1.4 1.4M15.6 4.4l-1.4 1.4M5.8 14.2l-1.4 1.4" />
    </svg>
  );
}

/**
 * Wraps the marketing page's center info sections with a self-contained
 * light/dark toggle. Only these children flip — via the `dark` class + the
 * `dark:` utilities on the sections — while the Capitol-backed hero and footer
 * live outside this wrapper and never change. State is local (resets on reload).
 */
// Tab motion — tweak these to taste once it's on screen.
const TAB_START_DEG = 68; // how far the tab is "swung out" at the top of the page
const TAB_SETTLE = 340; // px of scroll over which it rotates flush + eases down
const TAB_SLIDE = 44; // px it drifts downward as it settles

export function ThemedSection({ children }: { children: ReactNode }) {
  const [dark, setDark] = useState(false);
  const [scrollY, setScrollY] = useState(0);

  // Track scroll (rAF-throttled) so the tab's pivot follows the wheel smoothly.
  useEffect(() => {
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        setScrollY(window.scrollY);
        raf = 0;
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  // Tactile "page tab": hinged on its right edge against the viewport, it starts
  // swung out (as if peeling off the hero's bottom-right corner), then rotates
  // flush and eases downward as you scroll into the page.
  const progress = Math.min(1, scrollY / TAB_SETTLE);
  const rotate = TAB_START_DEG * (1 - progress);
  const slide = TAB_SLIDE * progress;

  return (
    <div className={`relative ${dark ? "dark" : ""}`}>
      <button
        type="button"
        onClick={() => setDark((d) => !d)}
        aria-pressed={dark}
        aria-label={dark ? "Switch this section to light mode" : "Switch this section to dark mode"}
        title={dark ? "Light mode" : "Dark mode"}
        style={{
          transform: `translateY(${slide}px) rotate(${rotate}deg)`,
          transformOrigin: "right center",
        }}
        className="fixed right-0 top-[22%] z-40 flex h-12 w-11 items-center justify-center rounded-l-2xl border border-r-0 border-slate-warm-300 bg-white/90 pr-1 text-slate-warm-600 shadow-lg backdrop-blur transition-colors hover:text-govnavy dark:border-white/20 dark:bg-govnavy/90 dark:text-white/85 dark:hover:text-white"
      >
        {dark ? <SunIcon /> : <MoonIcon />}
      </button>
      {children}
    </div>
  );
}
