"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, useState, useTransition, type FormEvent } from "react";

import { listQuery } from "@/lib/list-controls.mjs";

export type ListOption = { value: string; label: string };
export type ListField = {
  name: string;
  label: string;
  value?: string | number;
  options?: ListOption[];
  type?: "text" | "number";
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
  maxLength?: number;
  pattern?: string;
  disabled?: boolean;
  requires?: { name: string; value?: string }[];
};

const controlClass = "h-10 min-w-0 rounded-lg border border-line bg-canvas px-3 text-base text-ink outline-none focus:border-govblue-600 focus:ring-2 focus:ring-govblue-600/20 disabled:opacity-50 sm:text-sm";

export function ListToolbar({
  label,
  searchValue = "",
  searchPlaceholder = "Search this list",
  sorts,
  sortValue,
  fields = [],
  resetHref,
}: {
  label: string;
  searchValue?: string;
  searchPlaceholder?: string;
  sorts: ListOption[];
  sortValue: string;
  fields?: ListField[];
  resetHref?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const queryString = params.toString();
  const id = useId();
  const form = useRef<HTMLFormElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requested = useRef<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [validation, setValidation] = useState("");
  const defaults = JSON.stringify({ q: searchValue, sort: sortValue, ...Object.fromEntries(fields.map((field) => [field.name, String(field.value ?? "")])) });
  const activeFilters = fields.filter((field) => params.has(field.name)).length;

  useEffect(() => {
    function restore() {
      requested.current = null;
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
    }
    function leaving(event: MouseEvent) {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest("a") : null;
      if (link instanceof HTMLAnchorElement && link.target !== "_blank"
        && (link.pathname !== window.location.pathname || link.search !== window.location.search)) restore();
    }
    window.addEventListener("popstate", restore);
    document.addEventListener("click", leaving);
    return () => {
      window.removeEventListener("popstate", restore);
      document.removeEventListener("click", leaving);
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
    };
  }, []);

  useEffect(() => {
    if (timer.current !== null) return;
    // An older server response must not erase a newer draft or pending navigation.
    if (requested.current !== null && requested.current !== queryString) return;
    requested.current = null;
    const values: Record<string, string> = JSON.parse(defaults);
    for (const element of Array.from(form.current?.elements ?? [])) {
      if (element instanceof HTMLInputElement || element instanceof HTMLSelectElement) {
        if (document.activeElement !== element) element.value = values[element.name] ?? "";
      }
    }
  }, [queryString, defaults]);

  function apply() {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    if (!form.current) return;
    if (!form.current.checkValidity()) {
      const invalid = form.current.querySelector<HTMLInputElement>("input:invalid");
      setValidation(invalid?.validationMessage ?? "Complete or clear the invalid filters.");
      return;
    }
    setValidation("");
    const values = Array.from(new FormData(form.current).entries())
      .filter((entry): entry is [string, string] => typeof entry[1] === "string");
    const next = listQuery(
      window.location.search, values, ["q", "sort", ...fields.map((field) => field.name)],
      Object.fromEntries(fields.filter((field) => field.requires).map((field) => [field.name, field.requires ?? []])),
    );
    requested.current = next.toString();
    startTransition(() => router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false }));
  }

  function changed(event: FormEvent<HTMLFormElement>) {
    if (timer.current) clearTimeout(timer.current);
    const target = event.target;
    if (target instanceof HTMLSelectElement) apply();
    else timer.current = setTimeout(() => {
      timer.current = null;
      apply();
    }, 350);
  }

  return (
    <form
      ref={form}
      role="search"
      aria-label={label}
      aria-busy={pending}
      onChange={changed}
      onSubmit={(event) => {
        event.preventDefault();
        if (timer.current) clearTimeout(timer.current);
        apply();
      }}
      className="space-y-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <label className="min-w-[12rem] flex-1">
          <span className="sr-only">{label}</span>
          <input type="search" name="q" maxLength={100} defaultValue={searchValue} placeholder={searchPlaceholder} className={`${controlClass} w-full`} />
        </label>
        <label className="flex items-center gap-2 text-xs font-medium text-ink-soft">
          Sort
          <select name="sort" defaultValue={sortValue} className={`${controlClass} max-w-[13rem]`}>
            {sorts.map((sort) => <option key={sort.value} value={sort.value}>{sort.label}</option>)}
          </select>
        </label>
        <button
          type="button"
          className="h-10 rounded-lg px-3 text-sm font-semibold text-govblue-600 hover:bg-sunken focus-visible:outline focus-visible:outline-2"
          onClick={() => {
            if (timer.current) clearTimeout(timer.current);
            timer.current = null;
            requested.current = null;
            setValidation("");
            const reset = new URL(resetHref ?? pathname, window.location.origin);
            const next = listQuery(window.location.search, reset.searchParams, ["q", "sort", ...fields.map((field) => field.name)]);
            startTransition(() => router.replace(`${reset.pathname}${next.size ? `?${next}` : ""}`, { scroll: false }));
            form.current?.reset();
            if (form.current) {
              const search = form.current.elements.namedItem("q");
              if (search instanceof HTMLInputElement) search.value = "";
            }
          }}
        >Clear</button>
        <span role="status" className="min-w-16 text-xs text-ink-muted">{pending ? "Updating..." : ""}</span>
      </div>
      {fields.length > 0 && (
        <details className="rounded-lg border border-line bg-panel">
          <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-ink-soft">
            Filters{activeFilters > 0 ? ` (${activeFilters} active)` : ""}
          </summary>
          <div className="grid gap-3 border-t border-line p-3 sm:grid-cols-2 lg:grid-cols-4">
            {fields.map((field) => (
              <label key={field.name} htmlFor={`${id}-${field.name}`} className="flex min-w-0 flex-col gap-1 text-xs font-semibold text-ink-soft">
                {field.label}
                {field.options ? (
                  <select id={`${id}-${field.name}`} name={field.name} defaultValue={field.value ?? ""} disabled={field.disabled} className={controlClass}>
                    {field.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                ) : (
                  <input id={`${id}-${field.name}`} name={field.name} type={field.type ?? "text"} defaultValue={field.value ?? ""} placeholder={field.placeholder} min={field.min} max={field.max} step={field.step} maxLength={field.maxLength} pattern={field.pattern} disabled={field.disabled} className={controlClass} />
                )}
              </label>
            ))}
          </div>
        </details>
      )}
      {validation && <p role="alert" className="text-sm text-govred">{validation}</p>}
      <button type="submit" tabIndex={-1} className="sr-only">Search this list</button>
    </form>
  );
}
