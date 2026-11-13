"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type { ReactNode } from "react";

import { listPageHref } from "@/lib/list-controls.mjs";

export function ListPageLink({ href, className, children }: { href: string; className?: string; children: ReactNode }) {
  const params = useSearchParams();
  return <Link href={listPageHref(href, params.toString())} scroll={false} className={className}>{children}</Link>;
}
