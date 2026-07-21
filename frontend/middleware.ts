import { NextRequest, NextResponse } from "next/server";

/**
 * GovMap runs as a single Next.js deployment serving two logical zones from
 * one process: the marketing site at govmap.us (the real app/ root) and the
 * platform at app.govmap.us (files under app/app/, rewritten in transparently
 * here so the app zone's own URLs stay clean, e.g. app.govmap.us/members
 * rather than app.govmap.us/app/members).
 *
 * Locally, `*.localhost` always resolves to loopback with no hosts-file
 * edits needed, so the same split is exercised via:
 *   http://localhost:3000        -> marketing site
 *   http://app.localhost:3000    -> platform
 */
const APP_SUBDOMAIN_PREFIX = "app.";

export function middleware(request: NextRequest) {
  const host = request.headers.get("host") ?? "";
  const { pathname } = request.nextUrl;

  const isAppHost = host.startsWith(APP_SUBDOMAIN_PREFIX);
  if (isAppHost && !pathname.startsWith("/app")) {
    const url = request.nextUrl.clone();
    url.pathname = `/app${pathname}`;
    return NextResponse.rewrite(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)"],
};
