"use client";

import { usePathname } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  memberEntry,
  memberHref,
  memberLocation,
  withMemberEntry,
  type MemberEntry,
  type MemberLocation,
} from "@/lib/workspace-state";

type MemberBladeValue = {
  openId: string | null;
  entry: MemberEntry | null;
  open: (bioguide: string) => void;
  close: () => void;
  back: () => void;
  showDonations: () => void;
  toggleExpanded: () => void;
  saveScroll: (top: number) => void;
  notice: string | null;
  dismissNotice: () => void;
};

const MemberBladeContext = createContext<MemberBladeValue | null>(null);

function currentHref(): string {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

// randomUUID is unavailable outside secure contexts; entry ids only need to be unique per tab.
function newEntryId(): string {
  if (typeof window.crypto?.randomUUID === "function") return window.crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function MemberBladeProvider({ children }: { children: ReactNode }) {
  const [entry, setEntry] = useState<MemberEntry | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const pending = useRef(false);
  const scrollPositions = useRef(new Map<string, number>());
  const pathname = usePathname();

  const reportFailure = useCallback((error: unknown) => {
    console.warn("Member navigation failed:", error);
    pending.current = false;
    setNotice("This detail view could not be opened or restored. You can still use the member's direct link.");
  }, []);

  const sync = useCallback(() => {
    pending.current = false;
    try {
      const location = memberLocation(window.location.search);
      if (!location) {
        setEntry(null);
        return;
      }
      const href = currentHref();
      const previous = memberEntry(window.history.state, href);
      const next: MemberEntry = previous ? {
        ...previous,
        scrollTop: scrollPositions.current.get(previous.id) ?? previous.scrollTop,
      } : {
        ...location,
        version: 1,
        id: newEntryId(),
        href,
        origin: memberHref(href, null),
        depth: 0,
        scrollTop: 0,
      };
      if (!previous || previous.scrollTop !== next.scrollTop) {
        window.history.replaceState(withMemberEntry(window.history.state, next), "");
      }
      setEntry(next);
    } catch (error) {
      setEntry(null);
      reportFailure(error);
    }
  }, [reportFailure]);

  const flushScroll = useCallback(() => {
    try {
      const current = memberEntry(window.history.state, currentHref());
      const top = current ? scrollPositions.current.get(current.id) : undefined;
      if (current && top !== undefined && top !== current.scrollTop) {
        window.history.replaceState(
          withMemberEntry(window.history.state, { ...current, scrollTop: top }), "",
        );
      }
    } catch (error) {
      reportFailure(error);
    }
  }, [reportFailure]);

  useEffect(() => {
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, [pathname, sync]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "hidden") flushScroll();
    };
    document.addEventListener("click", flushScroll, true);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", flushScroll);
    return () => {
      document.removeEventListener("click", flushScroll, true);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", flushScroll);
    };
  }, [flushScroll]);

  const navigate = useCallback((location: MemberLocation) => {
    if (pending.current) return;
    try {
      flushScroll();
      const current = currentHref();
      const href = memberHref(current, location);
      if (href === current) return;
      const previous = memberEntry(window.history.state, current);
      const next: MemberEntry = {
        ...location,
        version: 1,
        id: newEntryId(),
        href,
        origin: previous?.origin ?? memberHref(current, null),
        depth: (previous?.depth ?? 0) + 1,
        scrollTop: previous?.member === location.member && previous.view === location.view
          ? previous.scrollTop : 0,
      };
      window.history.pushState(withMemberEntry(window.history.state, next), "", href);
      setEntry(next);
    } catch (error) {
      reportFailure(error);
    }
  }, [reportFailure, flushScroll]);

  const open = useCallback((bioguide: string) => {
    navigate({ member: bioguide, view: "profile", expanded: false });
  }, [navigate]);

  const leave = useCallback((all: boolean) => {
    if (pending.current) return;
    try {
      flushScroll();
      const current = memberEntry(window.history.state, currentHref());
      if (current && current.depth > 0) {
        pending.current = true;
        window.history.go(all ? -current.depth : -1);
      } else {
        window.history.replaceState(
          withMemberEntry(window.history.state, null),
          "",
          memberHref(currentHref(), null),
        );
        setEntry(null);
      }
    } catch (error) {
      reportFailure(error);
    }
  }, [reportFailure, flushScroll]);

  const close = useCallback(() => leave(true), [leave]);
  const back = useCallback(() => leave(false), [leave]);
  const showDonations = useCallback(() => {
    if (entry) navigate({ member: entry.member, view: "donations", expanded: entry.expanded });
  }, [entry, navigate]);
  const toggleExpanded = useCallback(() => {
    if (entry) navigate({ member: entry.member, view: entry.view, expanded: !entry.expanded });
  }, [entry, navigate]);
  const saveScroll = useCallback((top: number) => {
    try {
      const current = memberEntry(window.history.state, currentHref());
      if (!current) return;
      // Avoid history.replaceState on every scroll frame (browser rate limits).
      const positions = scrollPositions.current;
      positions.delete(current.id);
      positions.set(current.id, Math.max(0, top));
      if (positions.size > 100) {
        const oldest = positions.keys().next().value;
        if (oldest !== undefined) positions.delete(oldest);
      }
    } catch (error) {
      reportFailure(error);
    }
  }, [reportFailure]);
  const dismissNotice = useCallback(() => setNotice(null), []);

  const value = useMemo(
    () => ({ openId: entry?.member ?? null, entry, open, close, back, showDonations, toggleExpanded, saveScroll, notice, dismissNotice }),
    [entry, open, close, back, showDonations, toggleExpanded, saveScroll, notice, dismissNotice],
  );
  return (
    <MemberBladeContext.Provider value={value}>
      {children}
      {notice && !entry && (
        <div role="alert" className="fixed bottom-12 left-4 right-4 z-[80] mx-auto max-w-xl rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 shadow-lg">
          {notice}{" "}
          <button type="button" className="font-semibold underline" onClick={dismissNotice}>Dismiss</button>
        </div>
      )}
    </MemberBladeContext.Provider>
  );
}

export function useMemberBlade(): MemberBladeValue {
  const ctx = useContext(MemberBladeContext);
  if (!ctx) throw new Error("useMemberBlade must be used within a MemberBladeProvider");
  return ctx;
}
