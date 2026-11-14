"use client";

import { THEME_CHOICES } from "@/lib/theme.mjs";
import { setThemeChoice, useTheme } from "@/lib/use-theme";

const CHOICE_LABELS = { system: "System", light: "Light", dark: "Dark" } as const;

function SunIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      className="h-5 w-5"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5"
      aria-hidden="true"
    >
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
    </svg>
  );
}

/** Header button: flips whatever is showing now and remembers that choice. */
export function ThemeToggle() {
  const state = useTheme();
  // Same footprint before hydration, so the header doesn't shift.
  if (!state) return <span className="block h-9 w-9 shrink-0" aria-hidden="true" />;
  const next = state.theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => setThemeChoice(next)}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-slate-warm-600 transition-colors hover:bg-slate-warm-100 hover:text-govnavy"
    >
      {state.theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

/** Menu control: System, Light or Dark. System follows the device setting. */
export function ThemeMenuChoice({ tone = "chrome" }: { tone?: "chrome" | "panel" }) {
  const state = useTheme();
  const panel = tone === "panel";
  return (
    <fieldset className={panel ? "" : "px-3"}>
      <legend className={`pb-2 text-xs font-semibold uppercase tracking-wider ${panel ? "text-ink-muted" : "text-white/40"}`}>
        Theme
      </legend>
      <div className={`grid grid-cols-3 gap-1 rounded-lg border p-1 ${panel ? "border-line bg-sunken" : "border-white/10 bg-white/5"}`}>
        {THEME_CHOICES.map((choice) => (
          <label key={choice} className="cursor-pointer">
            <input
              type="radio"
              name="govmap-theme"
              value={choice}
              checked={state?.choice === choice}
              disabled={!state}
              onChange={() => setThemeChoice(choice)}
              className="peer sr-only"
            />
            <span className={`block rounded-md px-2 py-1.5 text-center text-sm font-medium transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-govblue ${panel ? "text-ink-soft hover:text-ink peer-checked:bg-panel peer-checked:text-ink peer-checked:shadow-sm" : "text-white/65 hover:text-white peer-checked:bg-white/15 peer-checked:text-white"}`}>
              {CHOICE_LABELS[choice]}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
