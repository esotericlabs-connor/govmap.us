"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { BladeDonations } from "@/components/BladeDonations";
import { MemberProfileBody } from "@/components/MemberProfileBody";
import { fetchMemberDetail, type MemberDetail } from "@/lib/api";
import { useMemberBlade } from "@/lib/member-blade";
import { useScrollLock } from "@/lib/use-scroll-lock";
import type { MemberEntry } from "@/lib/workspace-state";

function BladeSkeleton() {
  return (
    <div className="animate-pulse" role="status" aria-label="Loading member details">
      <div className="flex items-center gap-5">
        <div className="h-16 w-16 shrink-0 rounded-full bg-slate-warm-200" />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="h-3 w-24 rounded bg-slate-warm-200" />
          <div className="h-6 w-48 rounded bg-slate-warm-200" />
        </div>
      </div>
      <div className="mt-8 h-40 rounded-2xl bg-slate-warm-200" />
    </div>
  );
}

function MemberPanelBody({ entry }: { entry: MemberEntry }) {
  const { showDonations, saveScroll } = useMemberBlade();
  const [member, setMember] = useState<MemberDetail | null>(null);
  const [errored, setErrored] = useState(false);
  const [donationsVisited, setDonationsVisited] = useState(entry.view === "donations");
  const [donationsReady, setDonationsReady] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const restoredEntry = useRef<string | null>(null);
  const onDonationsReady = useCallback(() => setDonationsReady(true), []);

  useEffect(() => {
    const controller = new AbortController();
    fetchMemberDetail(entry.member, controller.signal).then((value) => {
      if (controller.signal.aborted) return;
      if (value) setMember(value);
      else setErrored(true);
    });
    return () => controller.abort();
  }, [entry.member]);

  useEffect(() => {
    if (entry.view === "donations") setDonationsVisited(true);
  }, [entry.view]);

  useLayoutEffect(() => {
    if (!member && !errored) return;
    if (entry.view === "donations" && !donationsReady && !errored) return;
    if (restoredEntry.current === entry.id) return;
    scrollRef.current?.scrollTo({ top: entry.scrollTop, behavior: "instant" });
    scrollRef.current?.focus({ preventScroll: true });
    restoredEntry.current = entry.id;
  }, [entry.id, entry.view, entry.scrollTop, member, errored, donationsReady]);

  return (
    <div
      ref={scrollRef}
      role="region"
      tabIndex={-1}
      aria-label={entry.view === "donations" ? "Member contributions" : "Member profile"}
      className="flex-1 overflow-y-auto overscroll-contain px-5 py-6 sm:px-6"
      onScroll={(event) => {
        if (restoredEntry.current === entry.id) saveScroll(event.currentTarget.scrollTop);
      }}
    >
      {errored ? (
        <div role="alert" className="py-10 text-center text-sm text-slate-warm-600">
          <p>This member&rsquo;s profile couldn&rsquo;t be loaded.</p>
          <Link href={`/members/${entry.member}`} className="mt-3 inline-block font-semibold text-govblue underline">
            Open the standalone profile
          </Link>
        </div>
      ) : member ? (
        <>
          <div hidden={entry.view !== "profile"}>
            <MemberProfileBody
              member={member}
              variant={entry.expanded ? "page" : "blade"}
              onViewDonations={showDonations}
            />
          </div>
          {(donationsVisited || entry.view === "donations") && (
            <div hidden={entry.view !== "donations"}>
              <BladeDonations member={member} onReady={onDonationsReady} />
            </div>
          )}
        </>
      ) : <BladeSkeleton />}
    </div>
  );
}

export function MemberBlade() {
  const { entry, back, close, toggleExpanded, notice, dismissNotice } = useMemberBlade();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const isOpen = entry !== null;
  useScrollLock(isOpen);

  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (isOpen && !dialog.open) {
      returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
    } else if (!isOpen && dialog.open) {
      dialog.close();
      if (returnFocus.current?.isConnected && !returnFocus.current.closest("[inert], [hidden]")) {
        returnFocus.current.focus({ preventScroll: true });
      } else {
        document.querySelector<HTMLElement>("[data-workspace-focus]")?.focus({ preventScroll: true });
      }
    }
  }, [isOpen]);

  if (typeof document === "undefined") return null;

  return createPortal(
    <dialog
      ref={dialogRef}
      aria-label="Member details"
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onClick={(event) => {
        if (event.target !== event.currentTarget) return;
        const bounds = event.currentTarget.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right ||
          event.clientY < bounds.top || event.clientY > bounds.bottom) close();
      }}
      className={`member-dialog fixed inset-y-0 left-auto right-0 m-0 h-dvh max-h-none w-full overflow-hidden border-l border-slate-warm-200 bg-slate-warm-50 p-0 text-slate-800 shadow-2xl backdrop:bg-govnavy/50 backdrop:backdrop-blur-sm ${
        entry?.expanded ? "max-w-6xl" : "max-w-[520px]"
      }`}
    >
      <div className="flex h-full flex-col">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-warm-200 bg-white px-5 py-3">
          <button type="button" onClick={back} className="text-sm font-semibold text-slate-warm-600 hover:text-govnavy">
            <span aria-hidden="true">&larr;</span> Back
          </button>
          <span className="text-xs text-slate-warm-500">
            Member{entry?.view === "donations" ? " / Contributions" : " / Profile"}
          </span>
          <div className="flex items-center gap-4">
            <button type="button" onClick={toggleExpanded} className="hidden text-sm font-semibold text-govblue hover:text-govnavy md:block">
              {entry?.expanded ? "Compact view" : "Expand"}
            </button>
            <button type="button" onClick={close} className="text-sm font-semibold text-slate-warm-600 hover:text-govnavy">
              Close
            </button>
          </div>
        </div>
        {notice && (
          <p role="alert" className="border-b border-amber-300 bg-amber-50 px-5 py-3 text-sm text-amber-950">
            {notice}{" "}
            <button type="button" className="font-semibold underline" onClick={dismissNotice}>Dismiss</button>
          </p>
        )}
        {entry && <MemberPanelBody key={entry.member} entry={entry} />}
      </div>
    </dialog>,
    document.body,
  );
}
