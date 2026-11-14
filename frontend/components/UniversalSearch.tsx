"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { MemberLink } from "@/components/MemberLink";
import { publicApiBase, type SearchResults } from "@/lib/api";
import { useMemberBlade } from "@/lib/member-blade";
import { matchSections } from "@/lib/sections";
import { useHomeZip } from "@/lib/zip-context";

/**
 * The platform's command bar. One box sets your area (a ZIP), jumps to any
 * section, and searches members, bills, votes and committees. It's an ARIA
 * combobox: ↑/↓ move through every suggestion, Enter opens the highlighted one
 * (the first, until you choose), Escape closes. Record search is debounced
 * and abortable; the query is URL-encoded and results render as escaped text.
 */

type OptionGroup = "zip" | "sections" | "members" | "bills" | "votes" | "committees";

type Option =
  | { kind: "zip"; group: "zip"; key: string; zip: string }
  | { kind: "member"; group: "members"; key: string; bioguide: string; label: string; meta: string }
  | {
      kind: "link";
      group: Exclude<OptionGroup, "zip" | "members">;
      key: string;
      href: string;
      label: string;
      meta?: string;
      description?: string;
      planned?: boolean;
      mono?: boolean;
    };

type RecordState = { term: string; results: SearchResults | null; errored: boolean };

const GROUP_LABELS: Record<OptionGroup, string> = {
  zip: "Your area",
  sections: "Sections",
  members: "Members",
  bills: "Bills",
  votes: "Votes",
  committees: "Committees",
};

const ZIP_PATTERN = /^\d{5}$/;

type Tone = "bar" | "chrome";
type ToneClasses = Record<
  "icon" | "input" | "kbd" | "panel" | "divider" | "strong" | "muted" | "faint" | "badge" | "active" | "idle",
  string
>;

/** "bar" sits on the themed header; "chrome" sits on the always-navy menu blade. */
const TONES: Record<Tone, ToneClasses> = {
  bar: {
    icon: "text-slate-warm-500",
    input:
      "border-slate-warm-300 bg-slate-warm-50 text-govnavy placeholder:text-slate-warm-500 hover:border-slate-warm-400 focus:border-govblue focus:bg-white",
    kbd: "border-slate-warm-300 text-slate-warm-500",
    panel: "border-slate-warm-200 bg-white text-slate-warm-700 shadow-card-hover",
    divider: "border-slate-warm-200",
    strong: "text-govnavy",
    muted: "text-slate-warm-500",
    faint: "text-slate-warm-400",
    badge: "border-slate-warm-300 text-slate-warm-500",
    active: "bg-slate-warm-100",
    idle: "hover:bg-slate-warm-50",
  },
  chrome: {
    icon: "text-white/70",
    input:
      "border-white/20 bg-white/10 text-white/90 placeholder:text-white/60 focus:border-white/50 focus:bg-white/20",
    kbd: "border-white/20 text-white/60",
    panel: "border-white/10 bg-govnavy-800/95 text-slate-200 shadow-2xl shadow-black/40 backdrop-blur-xl",
    divider: "border-white/10",
    strong: "text-white",
    muted: "text-slate-400",
    faint: "text-slate-500",
    badge: "border-white/15 text-white/50",
    active: "bg-white/10",
    idle: "hover:bg-white/5",
  },
};

function recordOptions(results: SearchResults): Option[] {
  return [
    ...results.members.map(
      (m): Option => ({
        kind: "member",
        group: "members",
        key: `member:${m.bioguide_id}`,
        bioguide: m.bioguide_id,
        label: m.official_full_name,
        meta: `${m.in_office === false ? "Former · " : ""}${m.party?.slice(0, 1) ?? ""} · ${m.state}`,
      }),
    ),
    ...results.bills.map((b): Option => {
      const code = `${b.bill_type.toUpperCase()} ${b.number}`;
      return {
        kind: "link",
        group: "bills",
        key: `bill:${b.bill_id}`,
        href: `/bills/${b.bill_id}`,
        label: b.title ?? code,
        meta: code,
        mono: true,
      };
    }),
    ...results.votes.map(
      (v): Option => ({
        kind: "link",
        group: "votes",
        key: `vote:${v.vote_id}`,
        href: `/votes/${v.vote_id}`,
        label: v.question ?? v.vote_id,
        meta: v.result ?? undefined,
      }),
    ),
    ...results.committees.map(
      (c): Option => ({
        kind: "link",
        group: "committees",
        key: `committee:${c.committee_id}`,
        href: `/committees/${c.committee_id}`,
        label: c.name,
      }),
    ),
  ];
}

function groupOptions(options: readonly Option[], firstIndex = 0) {
  const groups: { group: OptionGroup; items: { option: Option; index: number }[] }[] = [];
  options.forEach((option, i) => {
    const last = groups[groups.length - 1];
    const item = { option, index: firstIndex + i };
    if (last && last.group === option.group) last.items.push(item);
    else groups.push({ group: option.group, items: [item] });
  });
  return groups;
}

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT"
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}

function OptionBody({ option, t }: { option: Option; t: ToneClasses }) {
  if (option.kind === "zip") {
    return (
      <>
        <span aria-hidden="true">📍</span>
        <span className={`font-semibold ${t.strong}`}>Set {option.zip} as your area</span>
        <span className={`ml-auto shrink-0 text-xs ${t.muted}`}>find your reps →</span>
      </>
    );
  }
  if (option.kind === "link" && option.group === "sections") {
    return (
      <>
        <span className="min-w-0 flex-1">
          <span className={`block truncate font-semibold ${t.strong}`}>{option.label}</span>
          {option.description && (
            <span className={`block truncate text-xs ${t.muted}`}>{option.description}</span>
          )}
        </span>
        {option.planned ? (
          <span
            className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${t.badge}`}
          >
            Planned
          </span>
        ) : (
          <span className={`shrink-0 text-xs ${t.faint}`} aria-hidden="true">
            →
          </span>
        )}
      </>
    );
  }
  return (
    <>
      <span className={`truncate ${option.kind === "member" ? "font-semibold" : ""}`}>{option.label}</span>
      {option.meta && (
        <span
          className={`ml-auto shrink-0 text-xs ${t.muted} ${
            option.kind === "link" && option.mono ? "font-mono" : ""
          }`}
        >
          {option.meta}
        </span>
      )}
    </>
  );
}

const ROW_CLASS = "flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors";

export function UniversalSearch({
  className = "",
  onNavigate,
  shortcut = false,
  tone = "bar",
}: {
  className?: string;
  onNavigate?: () => void;
  /** Focus this box on "/" or Ctrl/⌘+K. Give it to one instance only. */
  shortcut?: boolean;
  tone?: Tone;
}) {
  const t = TONES[tone];
  const router = useRouter();
  const pathname = usePathname();
  const { open: openMember } = useMemberBlade();
  const { zip: homeZip, setHomeZip } = useHomeZip();
  const baseId = useId();
  const listId = `${baseId}-list`;
  const optionId = (index: number) => `${baseId}-opt-${index}`;
  const inputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  // The panel belongs to the page it was opened on, so Back/Forward closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [records, setRecords] = useState<RecordState | null>(null);

  const term = query.trim();
  const searchable = term.length >= 2;
  const open = openOn === pathname;
  const zipQuery = ZIP_PATTERN.test(term) ? term : null;

  // Debounced, abortable record search. State only changes once a response
  // (or a real failure) lands; "loading" is derived from the term mismatch.
  useEffect(() => {
    if (term.length < 2) return;
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${publicApiBase}/api/search?q=${encodeURIComponent(term)}`, {
          signal: ctrl.signal,
        });
        if (!res.ok) {
          setRecords({ term, results: null, errored: true });
          return;
        }
        setRecords({ term, results: (await res.json()) as SearchResults, errored: false });
      } catch (err) {
        // Aborts (a newer keystroke, or unmount) are expected; only real
        // network failures surface, so the panel never reads as "no results".
        if ((err as Error)?.name !== "AbortError") setRecords({ term, results: null, errored: true });
      }
    }, 220);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [term]);

  const current = searchable && records?.term === term ? records : null;
  const loading = searchable && current === null;
  // While the next query loads, the previous results stay visible but inert,
  // so Enter can never open a result for a query you've already changed.
  const stale = loading && records?.results ? records.results : null;

  const options: Option[] = [];
  if (zipQuery) options.push({ kind: "zip", group: "zip", key: `zip:${zipQuery}`, zip: zipQuery });
  if (!zipQuery) {
    for (const s of matchSections(term, term ? 4 : 6)) {
      options.push({
        kind: "link",
        group: "sections",
        key: `section:${s.id}`,
        href: s.href,
        label: s.label,
        description: s.description,
        planned: s.availability === "planned",
      });
    }
  }
  if (current?.results) options.push(...recordOptions(current.results));

  const chosen = activeKey === null ? -1 : options.findIndex((o) => o.key === activeKey);
  const activeIndex = chosen >= 0 ? chosen : term && options.length > 0 ? 0 : -1;
  const showPanel = open && (options.length > 0 || searchable);

  const recordCount = current?.results
    ? options.filter((o) => o.group !== "zip" && o.group !== "sections").length
    : 0;
  let status = "";
  if (loading) status = "Searching…";
  else if (current?.errored) status = "Search is unavailable right now — please try again.";
  else if (current && recordCount === 0 && !zipQuery)
    status = `No members, bills, votes or committees match “${term}”.`;

  useEffect(() => {
    if (!shortcut) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.isComposing) return;
      const commandK = (e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey;
      const slash = e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey && !isEditable(e.target);
      if (!commandK && !slash) return;
      const input = inputRef.current;
      // Hidden (narrow layout) or behind a modal: leave the key alone.
      if (!input || input.offsetParent === null) return;
      input.focus();
      if (document.activeElement !== input) return;
      e.preventDefault();
      input.select();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shortcut]);

  function finish() {
    setQuery("");
    setRecords(null);
    setActiveKey(null);
    setOpenOn(null);
    inputRef.current?.blur();
    onNavigate?.();
  }

  async function applyZip(zip: string) {
    if (!(await setHomeZip(zip))) return;
    // The overview has no map to fly to the new area, so show it on the map.
    if (pathname === "/") router.push("/map");
    finish();
  }

  function activate(option: Option) {
    if (option.kind === "zip") {
      void applyZip(option.zip);
      return;
    }
    if (option.kind === "member") openMember(option.bioguide);
    else router.push(option.href);
    finish();
  }

  function move(step: 1 | -1) {
    // A closed panel reopens first, keeping its default highlight.
    if (!showPanel) {
      setOpenOn(pathname);
      return;
    }
    if (options.length === 0) return;
    const next =
      activeIndex < 0
        ? step === 1
          ? 0
          : options.length - 1
        : (activeIndex + step + options.length) % options.length;
    setActiveKey(options[next].key);
    document.getElementById(optionId(next))?.scrollIntoView({ block: "nearest" });
  }

  function renderOption(option: Option, index: number) {
    const active = index === activeIndex;
    const shared = {
      id: optionId(index),
      role: "option" as const,
      "aria-selected": active,
      tabIndex: -1,
      onMouseMove: () => setActiveKey(option.key),
      className: `${ROW_CLASS} ${active ? t.active : t.idle}`,
    };
    if (option.kind === "zip") {
      const { zip } = option;
      return (
        <div
          key={option.key}
          {...shared}
          onClick={() => void applyZip(zip)}
          className={`${shared.className} cursor-pointer`}
        >
          <OptionBody option={option} t={t} />
        </div>
      );
    }
    if (option.kind === "member") {
      return (
        <MemberLink key={option.key} bioguide={option.bioguide} onClick={finish} {...shared}>
          <OptionBody option={option} t={t} />
        </MemberLink>
      );
    }
    return (
      <Link key={option.key} href={option.href} onClick={finish} {...shared}>
        <OptionBody option={option} t={t} />
      </Link>
    );
  }

  return (
    <div
      className={`relative ${className}`}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpenOn(null);
      }}
    >
      <form
        role="search"
        className="group relative flex items-center"
        onSubmit={(e) => {
          // A real submit is the one reliable path for the mobile keyboard's
          // Go/Search key, so Enter is handled here rather than on keydown.
          e.preventDefault();
          const option = open && activeIndex >= 0 ? options[activeIndex] : null;
          if (option) activate(option);
          else if (zipQuery) void applyZip(zipQuery);
        }}
      >
        <span className={`pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4 ${t.icon}`}>
          <SearchIcon />
        </span>
        <input
          ref={inputRef}
          type="search"
          role="combobox"
          enterKeyHint="search"
          autoComplete="off"
          spellCheck={false}
          value={query}
          aria-label="Search GovMap, jump to a section, or enter a ZIP code"
          aria-expanded={showPanel}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showPanel && activeIndex >= 0 ? optionId(activeIndex) : undefined}
          onChange={(e) => {
            const next = e.target.value;
            setQuery(next);
            setActiveKey(null);
            if (next.trim().length < 2) setRecords(null);
            setOpenOn(pathname);
          }}
          onFocus={() => setOpenOn(pathname)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              move(1);
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              move(-1);
            } else if (e.key === "Escape") {
              // Also keeps the browser from clearing the field.
              e.preventDefault();
              if (showPanel) {
                // Close just the suggestions, not the menu the box sits in.
                e.stopPropagation();
                setOpenOn(null);
                setActiveKey(null);
              } else {
                e.currentTarget.blur();
              }
            }
          }}
          placeholder="Search or enter a ZIP…"
          className={`w-full rounded-full border py-2 pl-11 transition-colors focus:outline-none focus:ring-2 focus:ring-govblue/70 ${t.input} ${
            shortcut ? "pr-4 md:pr-12" : "pr-4"
          } ${homeZip ? "" : "ring-2 ring-govblue/50"}`}
        />
        {shortcut && !query && (
          <kbd
            aria-hidden="true"
            className={`pointer-events-none absolute inset-y-0 right-3 my-auto hidden h-6 items-center rounded-md border px-2 font-mono text-xs md:flex ${t.kbd}`}
          >
            /
          </kbd>
        )}
      </form>

      {showPanel && (
        <div
          // Keeps focus in the input while an option is pressed, so the panel
          // can't close (on blur) before the click lands.
          onMouseDown={(e) => e.preventDefault()}
          className={`absolute left-0 right-0 top-full z-50 mt-2 max-h-[70vh] overflow-y-auto rounded-xl border animate-slide-down-and-fade ${t.panel}`}
        >
          <div id={listId} role="listbox" aria-label="Search suggestions" className="py-1">
            {groupOptions(options).map(({ group, items }) => (
              <SuggestionGroup
                key={group}
                id={`${baseId}-group-${group}`}
                label={group === "sections" && !term ? "Jump to" : GROUP_LABELS[group]}
                t={t}
              >
                {items.map(({ option, index }) => renderOption(option, index))}
              </SuggestionGroup>
            ))}
          </div>

          {stale && (
            <div inert aria-hidden="true" className="opacity-40">
              {groupOptions(recordOptions(stale)).map(({ group, items }) => (
                <div key={group} className={`border-t py-1 ${t.divider}`}>
                  <p className={`px-4 pb-1 pt-2 text-xs font-semibold uppercase tracking-wider ${t.muted}`}>
                    {GROUP_LABELS[group]}
                  </p>
                  {items.map(({ option }) => (
                    <div key={option.key} className={ROW_CLASS}>
                      <OptionBody option={option} t={t} />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}

          <p
            role="status"
            className={`flex items-center gap-2 px-4 text-sm ${t.muted} ${status ? `border-t py-3 ${t.divider}` : "sr-only"}`}
          >
            {loading && <Spinner />}
            {status || (recordCount > 0 ? `${recordCount} matching records` : "")}
          </p>

          <p
            aria-hidden="true"
            className={`hidden items-center gap-3 border-t px-4 py-2 text-[11px] md:flex ${t.divider} ${t.faint}`}
          >
            <span>↑↓ to move</span>
            <span>↵ to open</span>
            <span>esc to close</span>
          </p>
        </div>
      )}
    </div>
  );
}

function SuggestionGroup({
  id,
  label,
  t,
  children,
}: {
  id: string;
  label: string;
  t: ToneClasses;
  children: ReactNode;
}) {
  return (
    <div role="group" aria-labelledby={id} className={`border-b py-1 last:border-b-0 ${t.divider}`}>
      <div
        id={id}
        role="presentation"
        className={`px-4 pb-1 pt-2 text-xs font-semibold uppercase tracking-wider ${t.muted}`}
      >
        {label}
      </div>
      {children}
    </div>
  );
}
