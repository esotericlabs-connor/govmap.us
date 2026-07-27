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

/**
 * App-wide "which member is open in the slide-in blade." Every member link on
 * the site opens the blade instead of navigating, and the state is mirrored to
 * a `?member=<bioguide>` URL param so the blade is shareable and the browser
 * Back button closes it.
 *
 * The URL is driven with the History API — NOT `router.push` — on purpose:
 * `router.push` re-runs the current route's server components (e.g. a full
 * `/api/map` refetch under the map), which would reload/flash the page beneath
 * the blade. Native `pushState`/`replaceState` leaves the underlying page
 * completely untouched; we reconcile our own state from `popstate`.
 */

const PARAM = "member";

type MemberBladeValue = {
  openId: string | null;
  open: (bioguide: string) => void;
  close: () => void;
};

const MemberBladeContext = createContext<MemberBladeValue | null>(null);

function readParam(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get(PARAM);
}

// Current path + query with the member param set/cleared, preserving everything
// else (other params, hash).
function urlWith(id: string | null): string {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set(PARAM, id);
  else url.searchParams.delete(PARAM);
  return `${url.pathname}${url.search}${url.hash}`;
}

export function MemberBladeProvider({ children }: { children: ReactNode }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const openIdRef = useRef<string | null>(null);
  // Did *we* push a history entry for the current open blade? (vs. a deep-link
  // load, where there's no entry of ours to pop on close).
  const pushedRef = useRef(false);
  const pathname = usePathname();
  const lastPath = useRef(pathname);

  useEffect(() => {
    openIdRef.current = openId;
  }, [openId]);

  // Deep-link: open from ?member= on first mount.
  useEffect(() => {
    const initial = readParam();
    if (initial) {
      pushedRef.current = false;
      setOpenId(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reconcile with browser Back/Forward.
  useEffect(() => {
    const onPop = () => {
      pushedRef.current = false;
      setOpenId(readParam());
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // Close when the user actually navigates to another route.
  useEffect(() => {
    if (pathname !== lastPath.current) {
      lastPath.current = pathname;
      pushedRef.current = false;
      setOpenId(null);
    }
  }, [pathname]);

  const open = useCallback((bioguide: string) => {
    const current = openIdRef.current;
    if (current === bioguide) return;
    if (current === null) {
      window.history.pushState({ memberBlade: bioguide }, "", urlWith(bioguide));
      pushedRef.current = true;
    } else {
      // Swapping members while open — replace so Back still just closes.
      window.history.replaceState({ memberBlade: bioguide }, "", urlWith(bioguide));
    }
    setOpenId(bioguide);
  }, []);

  const close = useCallback(() => {
    if (pushedRef.current) {
      pushedRef.current = false;
      window.history.back(); // pops our entry → popstate clears openId
    } else {
      window.history.replaceState({}, "", urlWith(null));
      setOpenId(null);
    }
  }, []);

  const value = useMemo(() => ({ openId, open, close }), [openId, open, close]);

  return <MemberBladeContext.Provider value={value}>{children}</MemberBladeContext.Provider>;
}

export function useMemberBlade(): MemberBladeValue {
  const ctx = useContext(MemberBladeContext);
  if (!ctx) throw new Error("useMemberBlade must be used within a MemberBladeProvider");
  return ctx;
}
