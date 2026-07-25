"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { publicApiBase, type LookupResult } from "@/lib/api";

/**
 * App-wide "home area" the user has set by ZIP. Persisted to localStorage, so
 * the app always knows the user's ZIP/district until they change or clear it.
 * SSR-safe: the initial render is always empty (server + first client render
 * match), and the saved value is hydrated in an effect after mount — no
 * mismatch. Everything is fail-soft: a failed lookup just leaves the area unset.
 */

const STORAGE_KEY = "govmap_home_zip";
const ZIP_RE = /^\d{5}$/;

type ZipContextValue = {
  zip: string | null;
  result: LookupResult | null;
  loading: boolean;
  setHomeZip: (zip: string) => Promise<boolean>;
  clearHomeZip: () => void;
};

const ZipContext = createContext<ZipContextValue | null>(null);

async function lookupZip(zip: string): Promise<LookupResult | null> {
  try {
    const res = await fetch(`${publicApiBase}/api/lookup?zip=${zip}`);
    if (!res.ok) return null;
    const data = (await res.json()) as LookupResult;
    if (data.senators.length === 0 && data.representatives.length === 0) return null;
    return data;
  } catch {
    return null;
  }
}

export function ZipProvider({ children }: { children: ReactNode }) {
  const [zip, setZip] = useState<string | null>(null);
  const [result, setResult] = useState<LookupResult | null>(null);
  const [loading, setLoading] = useState(false);

  // Hydrate the saved ZIP after mount, then resolve its reps.
  useEffect(() => {
    const saved = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    if (!saved || !ZIP_RE.test(saved)) return;
    setZip(saved);
    setLoading(true);
    let alive = true;
    lookupZip(saved).then((r) => {
      if (!alive) return;
      setResult(r);
      setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, []);

  const setHomeZip = useCallback(async (next: string): Promise<boolean> => {
    if (!ZIP_RE.test(next)) return false;
    setLoading(true);
    const r = await lookupZip(next);
    setLoading(false);
    if (!r) return false;
    setZip(next);
    setResult(r);
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, next);
    return true;
  }, []);

  const clearHomeZip = useCallback(() => {
    setZip(null);
    setResult(null);
    if (typeof window !== "undefined") window.localStorage.removeItem(STORAGE_KEY);
  }, []);

  const value = useMemo(
    () => ({ zip, result, loading, setHomeZip, clearHomeZip }),
    [zip, result, loading, setHomeZip, clearHomeZip],
  );

  return <ZipContext.Provider value={value}>{children}</ZipContext.Provider>;
}

export function useHomeZip(): ZipContextValue {
  const ctx = useContext(ZipContext);
  if (!ctx) throw new Error("useHomeZip must be used within a ZipProvider");
  return ctx;
}
