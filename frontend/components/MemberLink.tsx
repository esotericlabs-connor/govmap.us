"use client";

import type { AnchorHTMLAttributes, ReactNode } from "react";

import { useMemberBlade } from "@/lib/member-blade";

type MemberLinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  bioguide: string;
  children: ReactNode;
};

/**
 * A member link that opens the slide-in profile blade instead of navigating.
 * Renders a real `<a href="/members/{id}">` so it stays crawlable and supports
 * open-in-new-tab / right-click; only a plain left-click is intercepted to open
 * the blade. Modifier and middle clicks fall through to normal navigation.
 */
export function MemberLink({ bioguide, children, onClick, ...rest }: MemberLinkProps) {
  const { open } = useMemberBlade();
  return (
    <a
      href={`/members/${bioguide}`}
      onClick={(e) => {
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        open(bioguide);
        onClick?.(e);
      }}
      {...rest}
    >
      {children}
    </a>
  );
}
