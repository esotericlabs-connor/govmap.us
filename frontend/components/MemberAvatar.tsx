"use client";

import { useState } from "react";

/**
 * Member portrait with a graceful fallback. Portraits come from
 * unitedstates/images and cover nearly all current members, but a brand-new
 * member can lag — if the image 404s (or there's no URL), we show their
 * initials instead of a broken-image icon. A plain <img> is used deliberately:
 * these are external, unoptimized thumbnails, so next/image would add config
 * and a domain allowlist for no benefit.
 */
export function MemberAvatar({
  src,
  name,
}: {
  src: string | null;
  name: string;
}) {
  const [failed, setFailed] = useState(false);

  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  if (!src || failed) {
    return (
      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-slate-200 text-sm font-semibold text-slate-500">
        {initials}
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={name}
      loading="lazy"
      onError={() => setFailed(true)}
      className="h-12 w-12 shrink-0 rounded-full object-cover"
    />
  );
}
