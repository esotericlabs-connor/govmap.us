"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";

import { publicApiBase } from "@/lib/api";
import {
  REPORT_CATEGORIES,
  REPORT_CATEGORY_NAMES,
  defaultCategoryForPath,
} from "@/lib/report-categories";

const MSG_MAX = 2000;

type Prefill = { category?: string; subcategory?: string; message?: string };

/**
 * "Report a problem" trigger + modal. Posts a category-tagged, page-aware report
 * to /api/report (the server scrubs + files it to bug_reports.log). Category is
 * pre-selected from the current path; `prefill` lets the error boundary seed it
 * with the crash. Nothing entered is ever shown back in the UI.
 */
export function BugReport({
  triggerClassName = "",
  triggerLabel = "Report a problem",
  prefill,
}: {
  triggerClassName?: string;
  triggerLabel?: string;
  prefill?: Prefill;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState("Other");
  const [subcategory, setSubcategory] = useState("Other");
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "done" | "error">("idle");

  const subcategories = REPORT_CATEGORIES[category] ?? ["Other"];

  function openModal() {
    const fromPath = defaultCategoryForPath(pathname);
    const wantCat = prefill?.category ?? fromPath.category;
    const cat = REPORT_CATEGORIES[wantCat] ? wantCat : "Other";
    const subs = REPORT_CATEGORIES[cat] ?? ["Other"];
    const wantSub = prefill?.subcategory ?? fromPath.subcategory;
    setCategory(cat);
    setSubcategory(subs.includes(wantSub) ? wantSub : subs[0]);
    setMessage((prefill?.message ?? "").slice(0, MSG_MAX));
    setStatus("idle");
    setOpen(true);
  }

  function onCategoryChange(next: string) {
    setCategory(next);
    setSubcategory((REPORT_CATEGORIES[next] ?? ["Other"])[0]);
  }

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const msg = message.trim();
    if (!msg) return;
    setStatus("sending");
    try {
      const res = await fetch(`${publicApiBase}/api/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category,
          subcategory,
          message: msg,
          url: typeof window !== "undefined" ? window.location.href : "",
        }),
      });
      setStatus(res.ok ? "done" : "error");
    } catch {
      setStatus("error");
    }
  }

  return (
    <>
      <button type="button" onClick={openModal} className={triggerClassName}>
        {triggerLabel}
      </button>

      {open &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center p-4"
            role="dialog"
            aria-modal="true"
            aria-label="Report a problem"
          >
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} aria-hidden="true" />
          <div className="relative w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
            {status === "done" ? (
              <div className="py-4 text-center">
                <h2 className="font-display text-xl font-bold text-govnavy">Thanks — report sent.</h2>
                <p className="mt-2 text-sm text-slate-warm-600">
                  We&apos;ll take a look. Nothing you entered is shown publicly.
                </p>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="mt-6 rounded-full bg-govnavy px-5 py-2 text-sm font-semibold text-white"
                >
                  Close
                </button>
              </div>
            ) : (
              <form onSubmit={onSubmit} className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="font-display text-xl font-bold text-govnavy">Report a problem</h2>
                  <button
                    type="button"
                    aria-label="Close"
                    onClick={() => setOpen(false)}
                    className="text-lg text-slate-warm-400 transition-colors hover:text-govnavy"
                  >
                    ✕
                  </button>
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label className="block text-sm">
                    <span className="font-medium text-slate-warm-600">Area</span>
                    <select
                      value={category}
                      onChange={(e) => onCategoryChange(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-slate-warm-200 bg-white px-3 py-2 text-sm text-slate-800"
                    >
                      {REPORT_CATEGORY_NAMES.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-sm">
                    <span className="font-medium text-slate-warm-600">Specifically</span>
                    <select
                      value={subcategory}
                      onChange={(e) => setSubcategory(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-slate-warm-200 bg-white px-3 py-2 text-sm text-slate-800"
                    >
                      {subcategories.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <label className="block text-sm">
                  <span className="font-medium text-slate-warm-600">What happened?</span>
                  <textarea
                    value={message}
                    onChange={(e) => setMessage(e.target.value.slice(0, MSG_MAX))}
                    rows={5}
                    required
                    placeholder="Describe the problem — what you expected vs. what you saw."
                    className="mt-1 w-full resize-none rounded-lg border border-slate-warm-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-govblue"
                  />
                  <span className="mt-1 block text-right text-xs text-slate-warm-400">
                    {message.length}/{MSG_MAX}
                  </span>
                </label>

                {status === "error" && (
                  <p className="text-sm font-medium text-govred">
                    Couldn&apos;t send — please try again in a moment.
                  </p>
                )}

                <div className="flex justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="rounded-full px-4 py-2 text-sm font-semibold text-slate-warm-600 transition-colors hover:text-govnavy"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={status === "sending" || !message.trim()}
                    className="rounded-full bg-govnavy px-5 py-2 text-sm font-semibold text-white transition-opacity disabled:opacity-60"
                  >
                    {status === "sending" ? "Sending…" : "Send report"}
                  </button>
                </div>
              </form>
            )}
          </div>
          </div>,
          document.body,
        )}
    </>
  );
}
