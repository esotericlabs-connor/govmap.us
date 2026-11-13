"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { BugReport } from "@/components/BugReport";
import { HomeZipChip } from "@/components/HomeZipChip";
import { ThemeMenuChoice } from "@/components/ThemeControls";
import { useHomeZip } from "@/lib/zip-context";

export function AppSettings({ open, onToggle, onClose }: {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const { zip } = useHomeZip();

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => titleRef.current?.focus());
    const onPointer = (event: PointerEvent) => {
      if (!(event.target instanceof Element) ||
        event.target.closest("dialog[open], [aria-modal='true']")) return;
      if (!rootRef.current?.contains(event.target)) onClose();
    };
    const onFocus = (event: FocusEvent) => {
      if (!(event.target instanceof Element) ||
        event.target.closest("dialog[open], [aria-modal='true']")) return;
      if (!rootRef.current?.contains(event.target)) onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" ||
        document.activeElement?.closest("dialog[open], [aria-modal='true']")) return;
      event.preventDefault();
      onClose();
      triggerRef.current?.focus();
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("focusin", onFocus);
    document.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("focusin", onFocus);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={onToggle}
        aria-label="Settings"
        aria-expanded={open}
        aria-controls="app-settings"
        aria-haspopup="dialog"
        className="flex h-9 w-9 items-center justify-center rounded-full text-slate-warm-600 transition-colors hover:bg-slate-warm-100 hover:text-govnavy"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-5 w-5" aria-hidden="true">
          <path strokeLinejoin="round" d="m9 3-.6 2.3-2 .9-2.2-.7-2 3.5 1.7 1.6v2.8L2.2 15l2 3.5 2.2-.7 2 .9L9 21h4l.6-2.3 2-.9 2.2.7 2-3.5-1.7-1.6v-2.8l1.7-1.6-2-3.5-2.2.7-2-.9L13 3Z" />
          <circle cx="11" cy="12" r="3" />
        </svg>
      </button>
      <section
        id="app-settings"
        hidden={!open}
        role="dialog"
        aria-labelledby="app-settings-title"
        className="fixed right-4 top-20 z-[52] max-h-[calc(100dvh-7rem)] w-[min(22rem,calc(100vw-2rem))] overflow-y-auto rounded-2xl border border-line bg-panel p-5 text-ink shadow-2xl sm:absolute sm:right-0 sm:top-full sm:mt-3"
      >
        <div className="mb-5 flex items-center justify-between gap-3">
          <h2 id="app-settings-title" ref={titleRef} tabIndex={-1} className="font-display text-lg font-bold">
            Settings
          </h2>
          <button type="button" onClick={() => {
            onClose();
            triggerRef.current?.focus();
          }} aria-label="Close settings" className="rounded-md px-2 py-1 text-ink-muted hover:text-ink">
            <span aria-hidden="true">&#215;</span>
          </button>
        </div>
        <ThemeMenuChoice tone="panel" />
        <div className="mt-5 border-t border-line pt-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">Home area</h3>
          {zip ? <HomeZipChip onNavigate={onClose} /> : (
            <p className="text-sm text-ink-soft">Use search to save your ZIP and find your representatives. On mobile, search is in the navigation menu.</p>
          )}
        </div>
        <div className="mt-5 border-t border-line pt-3">
          <Link href="/account" onClick={onClose} className="flex min-h-11 items-center justify-between gap-3 rounded-lg px-2 text-sm font-semibold hover:bg-sunken">
            Sign in
            <span className="rounded-full border border-line px-2 py-1 text-[10px] uppercase tracking-wide text-ink-muted">Coming soon</span>
          </Link>
          <p className="px-2 text-xs text-ink-muted">No account is needed to explore public records.</p>
        </div>
        <div className="mt-4 border-t border-line pt-3">
          <BugReport triggerLabel="Report a problem" triggerClassName="block min-h-11 w-full rounded-lg px-2 text-left text-sm font-semibold hover:bg-sunken" />
          <Link href="/privacy" onClick={onClose} className="flex min-h-11 items-center rounded-lg px-2 text-sm text-ink-soft hover:bg-sunken">Privacy & stored preferences</Link>
          <p className="mt-3 text-xs leading-relaxed text-ink-muted">Theme and home-area preferences are saved in this browser.</p>
        </div>
      </section>
    </div>
  );
}
