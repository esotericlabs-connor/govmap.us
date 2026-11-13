"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { moneyCandidateHref } from "@/lib/money-navigation.mjs";

export function RelatedCandidateLink({
  candidateId,
  cycle,
  returnTo,
  className,
}: {
  candidateId: string;
  cycle: number;
  returnTo: string;
  className?: string;
}) {
  const pathname = usePathname();
  const params = useSearchParams();
  const query = params.toString();
  const from = `${pathname}${query ? `?${query}` : ""}`;
  return (
    <Link className={className} href={moneyCandidateHref(candidateId, cycle, returnTo, from)}>
      {cycle}
    </Link>
  );
}
