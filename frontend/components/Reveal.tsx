"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Fades + lifts its children into view once they scroll near the viewport.
 * The content is always server-rendered in the DOM (only opacity/transform
 * animate), so it's SEO-safe and won't cause hydration mismatches. Motion is
 * disabled under `prefers-reduced-motion` (see globals.css .reveal rules).
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
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setVisible(true);
            observer.disconnect();
          }
        }
      },
      // threshold 0 = reveal as soon as the top edge enters. A percentage
      // threshold can NEVER be met by an element taller than the viewport
      // (e.g. the full members roster or a House roll call), which would leave
      // it stuck at opacity 0. The bottom rootMargin still delays short
      // below-the-fold sections until they're meaningfully in view.
      { threshold: 0, rootMargin: "0px 0px -10% 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`reveal${visible ? " is-visible" : ""} ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  );
}
