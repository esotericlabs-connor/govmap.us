"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

type Chamber = "house" | "senate";
type Tab = { label: string; chamber: Chamber | null };

const TABS: Tab[] = [
  { label: "All", chamber: null },
  { label: "House", chamber: "house" },
  { label: "Senate", chamber: "senate" },
];

export function ChamberTabs() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentChamber = searchParams.get("chamber");

  const tabsRef = useRef<(HTMLAnchorElement | null)[]>([]);
  const [gliderStyle, setGliderStyle] = useState({});

  useEffect(() => {
    const activeChamber =
      currentChamber === "house" || currentChamber === "senate" ? currentChamber : null;
    const activeTabIndex = TABS.findIndex((t) => t.chamber === activeChamber);
    const activeTab = tabsRef.current[activeTabIndex];

    if (activeTab) {
      setGliderStyle({
        left: activeTab.offsetLeft,
        width: activeTab.offsetWidth,
      });
    }
  }, [currentChamber]);

  return (
    <div className="relative inline-flex self-start rounded-full border border-slate-warm-200 bg-slate-warm-100 p-1">
      {TABS.map((tab, i) => {
        const active =
          (tab.chamber === null && !currentChamber) || tab.chamber === currentChamber;
        return (
          <Link
            key={tab.label}
            ref={(el) => (tabsRef.current[i] = el)}
            href={tab.chamber ? `${pathname}?chamber=${tab.chamber}` : pathname}
            className={`relative z-10 rounded-full px-5 py-1.5 text-sm font-semibold capitalize transition-colors duration-300 ${
              active ? "text-white" : "text-slate-warm-600 hover:text-govnavy"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
      <span
        className="absolute inset-y-1 z-0 rounded-full bg-govnavy shadow-md transition-all duration-300 ease-in-out"
        style={gliderStyle}
      />
    </div>
  );
}
