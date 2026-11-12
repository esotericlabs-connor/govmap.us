"use client";

import { usePathname } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";

import {
  defaultMapView,
  MAP_STORAGE_KEY,
  mapViewFromHistory,
  parseMapView,
  withMapView,
  type MapView,
} from "@/lib/workspace-state";

type MapWorkspaceValue = {
  view: MapView;
  setView: Dispatch<SetStateAction<MapView>>;
  ready: boolean;
  restored: boolean;
  revision: number;
  /** Records the latest handled home-ZIP selection; true when it differs from the last one. */
  claimHomeSelection: (version: number) => boolean;
  reset: () => void;
};

const MapWorkspaceContext = createContext<MapWorkspaceValue | null>(null);

export function MapWorkspaceProvider({ children }: { children: ReactNode }) {
  const [view, setView] = useState<MapView>(defaultMapView);
  const [ready, setReady] = useState(false);
  const [restored, setRestored] = useState(false);
  const [revision, setRevision] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const current = useRef(view);
  const canSave = useRef(false);
  const storageFailed = useRef(false);
  const visitedMap = useRef(false);
  const homeSelectionRef = useRef(0);
  const pathname = usePathname();

  // Lives here, not in the map, so remounting the map can't replay an old ZIP fly-to.
  const claimHomeSelection = useCallback((version: number) => {
    const changed = homeSelectionRef.current !== version;
    homeSelectionRef.current = version;
    return changed;
  }, []);

  useEffect(() => {
    if (pathname === "/") visitedMap.current = true;
    else if (visitedMap.current) setRestored(true);
  }, [pathname]);

  useLayoutEffect(() => {
    current.current = view;
  }, [view]);

  const reportFailure = useCallback((message: string, error: unknown) => {
    console.warn(`Map workspace: ${message}`, error);
    setNotice(message);
  }, []);

  const save = useCallback(() => {
    if (!canSave.current || window.location.pathname !== "/") return;
    try {
      // Keep Next.js's history metadata and any open detail's history entry.
      window.history.replaceState(withMapView(window.history.state, current.current), "");
    } catch (error) {
      reportFailure("The map's return position could not be saved.", error);
    }
    if (storageFailed.current) return;
    try {
      window.localStorage.setItem(MAP_STORAGE_KEY, JSON.stringify(current.current));
    } catch (error) {
      storageFailed.current = true;
      reportFailure("Your map view will be remembered in this tab only; browser storage is unavailable.", error);
    }
  }, [reportFailure]);

  useEffect(() => {
    let saved: MapView | null = null;
    try {
      saved = mapViewFromHistory(window.history.state);
    } catch (error) {
      reportFailure("An incompatible map return position was reset.", error);
    }
    if (!saved) {
      try {
        const stored = window.localStorage.getItem(MAP_STORAGE_KEY);
        if (stored) saved = parseMapView(JSON.parse(stored));
      } catch (error) {
        reportFailure("Your saved map view could not be restored. The default view is shown.", error);
      }
    }
    if (saved) {
      current.current = saved;
      setView(saved);
      setRestored(true);
    }
    canSave.current = true;
    setReady(true);

    const onPop = () => {
      // Do not save here: popstate already points at the destination entry.
      try {
        const previous = mapViewFromHistory(window.history.state);
        if (previous) {
          current.current = previous;
          setView(previous);
          setRestored(true);
          setRevision((value) => value + 1);
        }
      } catch (error) {
        reportFailure("This map return position is no longer available.", error);
      }
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") save();
    };
    // Capture before Next links or a member panel push their next history entry.
    document.addEventListener("click", save, true);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", save);
    window.addEventListener("popstate", onPop);
    return () => {
      canSave.current = false;
      document.removeEventListener("click", save, true);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", save);
      window.removeEventListener("popstate", onPop);
    };
  }, [reportFailure, save]);

  useEffect(() => {
    if (!ready) return;
    const timer = window.setTimeout(save, 180);
    return () => window.clearTimeout(timer);
  }, [view, ready, save]);

  const reset = useCallback(() => {
    const next = defaultMapView();
    current.current = next;
    setView(next);
    setRestored(true);
    setRevision((value) => value + 1);
  }, []);

  const value = useMemo(
    () => ({ view, setView, ready, restored, revision, claimHomeSelection, reset }),
    [view, ready, restored, revision, claimHomeSelection, reset],
  );

  return (
    <MapWorkspaceContext.Provider value={value}>
      {children}
      {notice && (
        <div role="status" className="fixed bottom-12 left-4 right-4 z-[80] mx-auto flex max-w-xl items-start gap-4 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 shadow-lg">
          <p>{notice}</p>
          <button type="button" className="ml-auto shrink-0 font-semibold underline" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}
    </MapWorkspaceContext.Provider>
  );
}

export function useMapWorkspace(): MapWorkspaceValue {
  const value = useContext(MapWorkspaceContext);
  if (!value) throw new Error("useMapWorkspace must be used within a MapWorkspaceProvider");
  return value;
}
