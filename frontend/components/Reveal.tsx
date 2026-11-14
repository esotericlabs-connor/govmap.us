import type { ReactNode } from "react";

const MAX_DELAY_MS = 300;

/**
 * Visible from the server render, with a small entrance lift but no opacity
 * gate or scroll observer. Capped delays never hide long lists or restored
 * scroll positions. Reduced motion is handled in globals.css.
 */
export function Reveal({
  children,
  className = "",
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <div
      className={`animate-reveal ${className}`}
      style={delay > 0 ? { animationDelay: `${Math.min(delay, MAX_DELAY_MS)}ms` } : undefined}
    >
      {children}
    </div>
  );
}
