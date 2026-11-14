"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { MapStatusBar } from "@/components/MapStatusBar";
import { publicApiBase, type ChamberSummary } from "@/lib/api";
import { parseChamberSummary } from "@/lib/chamber-summary";
import { isWorkspacePath } from "@/lib/sections";

function WorkspaceStatusBar({ pathname }: { pathname: string }) {
  const [summary, setSummary] = useState<ChamberSummary | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    const timeout = window.setTimeout(() => controller.abort(), 10_000);
    setSummary(null);
    setStatus("loading");
    fetch(`${publicApiBase}/api/summary`, { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Chamber summary request failed: ${response.status}`);
        const data = parseChamberSummary(await response.json());
        if (!controller.signal.aborted) {
          setSummary(data);
          setStatus("ready");
        }
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      })
      .finally(() => window.clearTimeout(timeout));
    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [pathname, retry]);

  return (
    <MapStatusBar
      key={pathname}
      summary={summary}
      status={status}
      onRetry={() => setRetry((value) => value + 1)}
    />
  );
}

export function WorkspaceChrome({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const workspace = isWorkspacePath(pathname);
  return (
    <>
      <div className={workspace ? "pb-[var(--workspace-bar-height)]" : undefined}>{children}</div>
      {workspace && <WorkspaceStatusBar pathname={pathname} />}
    </>
  );
}
