import { useSyncExternalStore } from "react";

import {
  parseThemeChoice,
  resolveTheme,
  THEME_STORAGE_KEY,
  type Theme,
  type ThemeChoice,
} from "@/lib/theme.mjs";

export type ThemeState = { choice: ThemeChoice; theme: Theme };

const DARK_QUERY = "(prefers-color-scheme: dark)";
const listeners = new Set<() => void>();

// <html data-theme> is the source of truth: the first-paint script sets it from
// storage, and the CSS reads it. No attribute means "follow the system".
function applyToRoot(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") delete root.dataset.theme;
  else root.dataset.theme = choice;
}

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia(DARK_QUERY);
  // A choice made in another tab applies here too.
  const onStorage = (event: StorageEvent) => {
    if (event.key !== null && event.key !== THEME_STORAGE_KEY) return;
    applyToRoot(parseThemeChoice(event.newValue));
    onChange();
  };
  listeners.add(onChange);
  media.addEventListener("change", onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onChange);
    media.removeEventListener("change", onChange);
    window.removeEventListener("storage", onStorage);
  };
}

function snapshot(): string {
  const choice = parseThemeChoice(document.documentElement.dataset.theme);
  return `${choice}:${resolveTheme(choice, window.matchMedia(DARK_QUERY).matches)}`;
}

// The server can't know the saved choice or the system setting.
function serverSnapshot(): string {
  return "";
}

export function setThemeChoice(choice: ThemeChoice): void {
  applyToRoot(choice);
  try {
    if (choice === "system") localStorage.removeItem(THEME_STORAGE_KEY);
    else localStorage.setItem(THEME_STORAGE_KEY, choice);
  } catch (error) {
    console.warn("Theme: couldn't save the choice; it applies until this page closes.", error);
  }
  for (const listener of listeners) listener();
}

/** The current theme, or null before hydration (render a same-size placeholder). */
export function useTheme(): ThemeState | null {
  const value = useSyncExternalStore(subscribe, snapshot, serverSnapshot);
  if (!value) return null;
  const [choice, theme] = value.split(":");
  return { choice: parseThemeChoice(choice), theme: theme === "dark" ? "dark" : "light" };
}
