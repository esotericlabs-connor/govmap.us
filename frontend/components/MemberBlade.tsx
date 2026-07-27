"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { MemberProfileBody } from "@/components/MemberProfileBody";
import { fetchMemberDetail, type MemberDetail } from "@/lib/api";
import { useMemberBlade } from "@/lib/member-blade";

function BladeSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="flex items-center gap-5">
        <div className="h-16 w-16 shrink-0 rounded-full bg-slate-warm-200" />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="h-3 w-24 rounded bg-slate-warm-200" />
          <div className="h-6 w-48 rounded bg-slate-warm-200" />
          <div className="h-3 w-32 rounded bg-slate-warm-200" />
        </div>
      </div>
      <div className="mt-8 grid grid-cols-2 gap-6">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <div className="h-2.5 w-16 rounded bg-slate-warm-200" />
            <div className="h-4 w-24 rounded bg-slate-warm-200" />
          </div>
        ))}
      </div>
      <div className="mt-8 h-40 rounded-2xl bg-slate-warm-200" />
    </div>
  );
}

function BladeError({ bioguide }: { bioguide: string }) {
  return (
    <div className="mt-10 text-center">
      <p className="text-sm text-slate-warm-500">This member&rsquo;s profile couldn&rsquo;t be loaded.</p>
      <Link
        href={`/members/${bioguide}`}
        className="mt-3 inline-block rounded-full border border-slate-warm-200 px-4 py-2 text-sm font-semibold text-slate-warm-700 transition-colors hover:border-govnavy hover:text-govnavy"
      >
        Open the full page instead ↗
      </Link>
    </div>
  );
}

/**
 * The site-wide member profile blade. Mounted once (under MemberBladeProvider);
 * slides in from the right whenever a member link is clicked. Portaled to
 * <body> so no ancestor's transform/backdrop-filter can clip a `fixed` panel,
 * and always mounted so the slide transition animates.
 */
export function MemberBlade() {
  const { openId, close } = useMemberBlade();
  const [member, setMember] = useState<MemberDetail | null>(null);
  const [errored, setErrored] = useState(false);

  // Fetch the full profile whenever the open member changes.
  useEffect(() => {
    if (!openId) return;
    let alive = true;
    setMember(null);
    setErrored(false);
    fetchMemberDetail(openId).then((m) => {
      if (!alive) return;
      if (m) setMember(m);
      else setErrored(true);
    });
    return () => {
      alive = false;
    };
  }, [openId]);

  // Lock body scroll + wire Escape while open.
  useEffect(() => {
    if (!openId) return;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [openId, close]);

  if (typeof document === "undefined") return null;

  const isOpen = openId !== null;

  return createPortal(
    <>
      {/* Backdrop — always mounted so it fades; pointer-events off when closed. */}
      <div
        className={`fixed inset-0 z-[65] bg-govnavy/50 backdrop-blur-sm transition-opacity duration-300 ${
          isOpen ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={close}
        aria-hidden="true"
      />
      {/* Right-side blade. */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Member profile"
        aria-hidden={!isOpen}
        className={`fixed inset-y-0 right-0 z-[70] flex w-full max-w-[520px] transform flex-col border-l border-slate-warm-200 bg-slate-warm-50 shadow-2xl transition-transform duration-300 ease-out ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between border-b border-slate-warm-200 bg-white/70 px-5 py-3 backdrop-blur">
          <button
            type="button"
            onClick={close}
            className="flex items-center gap-1.5 text-sm font-semibold text-slate-warm-600 transition-colors hover:text-govnavy"
          >
            <span aria-hidden="true">←</span> Close
          </button>
          {openId && (
            <Link
              href={`/members/${openId}`}
              className="text-sm font-medium text-govblue transition-colors hover:text-govnavy"
            >
              Open full page ↗
            </Link>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-6 sm:px-6">
          {errored && openId ? (
            <BladeError bioguide={openId} />
          ) : member ? (
            <MemberProfileBody member={member} variant="blade" />
          ) : (
            <BladeSkeleton />
          )}
        </div>
      </aside>
    </>,
    document.body,
  );
}
