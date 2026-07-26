"use client";

import { useState, type ReactNode } from "react";

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
export function ThemedSection({ children }: { children: ReactNode }) {
  const [dark, setDark] = useState(false);

  return (
    <div className={`relative ${dark ? "dark" : ""}`}>
      {/* Toggle pinned to the top-right of the centered content column. The
          strip is click-through; only the button itself is interactive. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-20">
        <div className="mx-auto flex max-w-6xl justify-end px-6 pt-6">
          <button
            type="button"
            onClick={() => setDark((d) => !d)}
            aria-pressed={dark}
            aria-label={dark ? "Switch this section to light mode" : "Switch this section to dark mode"}
            title={dark ? "Light mode" : "Dark mode"}
            className="pointer-events-auto flex h-10 w-10 items-center justify-center rounded-full border border-slate-warm-300 bg-white/80 text-slate-warm-600 shadow-sm backdrop-blur transition-colors hover:text-govnavy dark:border-white/20 dark:bg-white/10 dark:text-white/80 dark:hover:text-white"
          >
            {dark ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </div>
      {children}
    </div>
  );
}
