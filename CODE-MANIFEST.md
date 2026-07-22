# CODE-MANIFEST.md

What's been built, in what order, and what's next. This is a living log — add an entry every time a meaningful piece of the build lands. For what GovMap is, see [README.md](README.md). For how it gets built, see [AGENTS.md](AGENTS.md).

## Build log

**2026-07-22 — Design system + landing/app polish pass**
Comprehensive front-end design pass establishing a shared system the whole app inherits. Typography via `next/font` (Space Grotesk display + Inter body → CSS vars, wired into Tailwind `fontFamily`). New shared components: `SiteHeader` (fixed, glass-on-scroll, mobile hamburger; `marketing`/`app` variants), `SiteFooter` (Capitol backdrop, Explore/Project/Legal columns, social icons), `Reveal` (IntersectionObserver scroll-fade, reduced-motion-safe), `LegalLayout`. Landing hero gets a staggered on-load fade-up (pure CSS) and stronger scrim; About/Support fade in on scroll. Draft `/privacy` and `/security` pages. Root body is now navy so mobile overscroll blends into the dark hero/footer (iOS paints only the root bg-color in the rubber-band, so color-matching is the reliable fix). Added OpenGraph/Twitter card metadata (Capitol image) for rich social shares. Social links are placeholder `@govmapus` (X/Bluesky/Instagram) pending real accounts. Tokens: `govnavy-800`, `fade-up`/`fade-in` keyframes, `shadow-card`. No new runtime dependencies (motion is CSS + a tiny observer; icons stay inlined). **Note:** `next/font/google` fetches fonts at build time — the Docker build needs network (it already has it for npm).

**2026-07-22 — Landing page: Capitol hero, transparent logo, support links**
Redesigned the marketing hero with a US Capitol sunset photo (`public/capitol-hero.jpg`) behind a navy gradient for legibility. Fixed the "off-color box" logo: the logo PNG's baked background is `#0A0E1E` but the page navy is `#070B1A`, so it read as a rectangle — generated `logo-dark-transparent.png` (alpha-keyed the dark background out, verified clean) and use it as the home-button logo everywhere on dark surfaces; the opaque `logo-dark.png`/`logo-light.png` are kept as the primary brand assets. Added a Support section with six active donation platforms (Patreon, Ko-fi, Buy Me a Coffee, Liberapay, Open Collective, thanks.dev) rendered with Simple Icons brand glyphs (`components/BrandIcon.tsx`, inlined — no icon dependency), plus a **"seeking a fiscal sponsor"** callout. `site-config` gained `supportLinks[]`; the unused `supportUrl` was removed.

**2026-07-22 — Redeploy hardening + full stack live in production**
Site live end-to-end at govmap.us through the dashboard-managed tunnel (marketing, `/members` with real portraits + party colors, 537 members). Made redeploy fully reproducible: root `.env.example` documents the two required secrets (`POSTGRES_PASSWORD`, `CLOUDFLARE_TUNNEL_TOKEN`); `deploy.sh` now writes a self-documenting `.env` on a fresh box and flags the missing tunnel token; README gained a "Rebuilding on a fresh box" runbook. **Key operational fact: the tunnel is dashboard-managed, so its routes live in Cloudflare and survive any rebuild — the only per-box state is `.env`.** Reconnecting a rebuilt box = restore `.env` (or re-fetch the token from the CF dashboard) + `bash scripts/deploy.sh`. Tunnel ID `ebdeb681-961d-4321-8beb-2f14b35c6143`.

**2026-07-22 — Cloudflare Tunnel as a stack service**
Moved the tunnel from a per-box systemd unit (fragile: interactive `tunnel login`, on-disk credentials that can't live in the repo, and the source of a rebuild's Error 1033) into the compose stack. New `cloudflared` service runs a **dashboard-managed** tunnel via a token from `.env` (`CLOUDFLARE_TUNNEL_TOKEN`), under a `tunnel` compose profile that `scripts/deploy.sh` enables automatically when the token is present. So `docker compose up` now brings the public site up too, and rebuilding a box is just "restore the token to `.env`." Ingress (public hostnames → `http://frontend:3000` / `http://backend:8000`) is configured once in the Cloudflare Zero Trust dashboard; cloudflared shares the compose network so those service names resolve. The old CLI/systemd tunnel should be uninstalled (`sudo cloudflared service uninstall`) and its dashboard tunnel deleted.

**2026-07-21 — Single-source deploy script**
Added `scripts/deploy.sh` as the one deploy path: `git reset --hard origin/main` → ensure `.env` (generates `POSTGRES_PASSWORD` if missing) → `docker compose up -d --build` → poll `/health` (backend migrates on start) → refresh data (pipeline + normalize, non-fatal so a source outage can't fail the deploy) → prune → verify `photo_url` is populated. Idempotent, re-runnable, never touches `.env` or the Postgres volume. Takes `--no-data` for code-only changes. The GitHub Actions runner now just calls `bash /opt/govmap/scripts/deploy.sh`, so manual and automated deploys are literally the same script — no more copy-pasted command sequences, and a reliable manual deploy exists whenever the runner is down.

**2026-07-21 — Member photos + roster polish + branding**
Swapped `logo-dark.png`/`logo-light.png` for tight cropped lockups (the originals had large baked-in margins that made the wordmark render tiny) and resized every logo `<Image>` to the new ~3.13:1 aspect. Added **member portraits**: `normalize/members.py` now sets `photo_url` to the deterministic unitedstates/images URL (`https://unitedstates.github.io/images/congress/225x275/{bioguide}.jpg`, verified 200 image/jpeg) — no separate pull pipeline since the URL is fully derivable from the Bioguide ID. The roster renders them via a small `MemberAvatar` client component that falls back to initials on 404/missing, plus party-colored labels (govred/govblue). Added a targeted `.gitattributes` (LF for `*.sh`/`*.yml`/`Dockerfile`, binary for images) to end the CRLF churn and guarantee the deploy script stays LF on the Linux host.

Note: `photo_url` was previously left null by the normalizer (it was reserved for a separate images pipeline). Setting it deterministically means an existing DB needs one normalize run to backfill — future weekly scheduler runs handle it automatically.

**2026-07-21 — Closed the operational loop**
With the pipeline proven live, automated the parts that were manual. (1) **Auto-deploy**: `.github/workflows/deploy.yml` now runs on push to `main` via a self-hosted GitHub Actions runner on the VM — it `git reset --hard`s `/opt/govmap` to `origin/main` and `docker compose up -d --build`s (backend re-applies Alembic migrations on start). No SSH, no exposed ports. Runner install is a one-time server-side step (needs a GitHub registration token). (2) **Scheduler**: `backend/app/scheduler.py` (APScheduler, wired into the FastAPI lifespan) refreshes members weekly (Sun 07:00 UTC) so data no longer depends on a manual run. (3) **Secured `/internal/*`**: HTTP Basic Auth via `INTERNAL_USER`/`INTERNAL_PASSWORD`, locked by default when unset — it was reachable at `api.govmap.us/internal/*` with no auth. (4) **Fixed the roster cap**: the members query was hardcoded to `limit=535`, silently hiding the ~2 non-voting delegates the pipeline loads (537 total); raised to 600 on both API and frontend. Nightly `pg_dump` backups remain a server-side cron (see server hardening notes).

**2026-07-21 — Flattened frontend routing (fixed blank-page bug)**
The first deploy rendered blank: every page served HTML with no `<!DOCTYPE html>`/`<html>`/`<body>` (Quirks Mode + React #418/#423 hydration failure → React tore the tree down). Ruled out Cloudflare (Bot Fight Mode / JS Detections injection was a real but secondary red herring) and the middleware (removing it didn't help). Root cause: **the platform routes lived under `app/app/` — a route segment literally named `app` inside the App Router's own `app/` directory — which corrupted route resolution so Next.js used `app/app/layout.tsx` (a bare `<div>`, no `<html>`) as the root and skipped the real `app/layout.tsx` entirely.**

Fix: collapsed to a standard flat structure — marketing at `app/page.tsx` (`/`), members at `app/members/page.tsx` (`/members`), no nested `app/app/`, no middleware. **Deferred: the govmap.us / app.govmap.us subdomain split.** It required host-based rewriting (middleware or `app/app/` nesting) and was the source of this whole class of pain; re-introduce it only once the flat app is proven stable, using a tested approach (config-level `rewrites` or separate concerns). `cloudflared` still routes `app.govmap.us` → `localhost:3000`, which now just serves the same content as `govmap.us` — harmless; drop that ingress line when convenient. `middleware.ts` and `site-config`'s subdomain URLs were removed.

**2026-07-21 — Containerized deploy layer**
Added `backend/Dockerfile` (migrations-on-start + uvicorn, non-root) and a multi-stage `frontend/Dockerfile` (Next.js `standalone` output, non-root runner). Extended `docker-compose.yml` from Postgres-only to the full stack: `postgres` + `backend` (`127.0.0.1:8000`) + `frontend` (`127.0.0.1:3000`), all loopback-bound so `cloudflared` reaches them over localhost and nothing is publicly exposed. Server-side rendering in the frontend now reaches the backend over the internal compose network (`API_INTERNAL_URL=http://backend:8000`); `NEXT_PUBLIC_*` prod URLs are baked at build time via compose build args. First real production deploy target: the home Ubuntu VM behind the `govmap` cloudflared tunnel (govmap.us / app.govmap.us / api.govmap.us).

**2026-07-20 — Brand assets + marketing/platform split**
Received the first brand assets: `logo-dark.png` / `logo-light.png` (full lockups, opaque backgrounds baked in — not transparent, so they're placed as full-bleed treatments, not floated over arbitrary backgrounds). Sampled exact colors from the artwork rather than eyeballing hex values: navy `#070B1A`, red `#DD1922`, blue `#58A9E6`, now in `frontend/tailwind.config.ts` as `govnavy`/`govred`/`govblue`. Cropped a square Capitol-only mark from the dark logo (no source icon-only asset existed) for `frontend/app/icon.png`.

Split the frontend into two zones on one Next.js deployment: **govmap.us** (marketing site, `app/page.tsx`) and **app.govmap.us** (the platform, moved to `app/app/`), routed by hostname in `frontend/middleware.ts`. Cross-zone links (marketing's "Enter GovMap" button, the platform header's link back) go through `frontend/lib/site-config.ts` since they need to be absolute URLs, not relative paths, once the two zones are on different hosts in production. Social handles and a support/donation link are left empty in that config — nothing fake ships in the footer.

**2026-07-20 — Repo scaffold + pilot pipeline started**
Consolidated the original planning notes (six documents, written across earlier drafts with some mutual inconsistencies — see *Reconciliation notes* below) into this file, `README.md`, and `AGENTS.md`. Decided to prove the full pipeline contract (pull → validate → normalize → store → serve → display) on a single source — `congress-legislators` — end-to-end through a minimal FastAPI + Next.js stack, before parallelizing to the remaining 24 sources. LLM summarization and Redis caching are explicitly deferred (see `AGENTS.md` → Current explicit boundaries).

## Reconciliation notes

The original planning docs disagreed with each other in a few places. Resolved as follows:

- **Source count**: 25 sources (confirmed against the masterlist's own "25 total" tally).
- **JSON output count**: 24 canonical outputs — 23 domain outputs plus `pipeline_status.json` as the operational/health output. (One earlier doc's table listed only 23 total because it predated the addition of the Senate LDA and Financial Disclosures sources; another doc's checklist heading said "23 JSON output" but its own criteria table lists 24 — that was a leftover from before those two sources were added, not a real disagreement.)
- **Senate LDA source**: the original note that `lda.senate.gov` "shuts down June 30 2026" is confirmed and the site now redirects to **lda.gov**, with API docs at `lda.senate.gov/api/`. Build the `senate_lda.py` pipeline against the current `lda.gov` endpoint, not the legacy domain. API access is already in hand.
- **Repo folder structure doc**: discarded. It was carried over from an unrelated project (financial dashboard) and doesn't fit GovMap's domain. The structure actually in use is documented below under *Repository layout*.
- **Frontend framework**: Next.js (App Router), not the earlier draft's Vite + React Router.
- **Hosting**: self-hosted home VM behind `cloudflared` (no exposed ports), Tailscale-only SSH, GitHub Actions deploy — not the earlier draft's Hetzner VPS + Coolify. This is a deliberate cheap-and-temporary choice; see README's Tech stack section.
- **OpenSecrets bulk data license** ("free, non-commercial") confirmed compatible with GovMap's nonprofit, non-advertising model.

## Canonical source list (25)

Status: `pilot` = actively being built against right now, `planned` = designed for, not yet started, `on hold` = deferred by product decision (not blocked technically).

| # | Source | Branch/category | Status |
| --- | --- | --- | --- |
| 1 | Congress.gov API | Legislative | planned |
| 2 | unitedstates/congress-legislators | Legislative | **pilot** |
| 3 | unitedstates/congress (scrapers) | Legislative | planned |
| 4 | unitedstates/images | Legislative | planned |
| 5 | FEC API | Legislative/Executive | planned |
| 6 | OpenSecrets bulk data | Legislative | planned |
| 7 | Federal Register API | Executive | planned |
| 8 | SAM.gov Federal Hierarchy API | Executive | planned |
| 9 | OPM PLUM website | Executive | planned |
| 10 | USASpending.gov API | Executive | planned |
| 11 | CourtListener API | Judicial | planned |
| 12 | Free Law Project judge photos | Judicial | planned |
| 13 | Census Data API | Geographic | planned |
| 14 | Open States API | State legislative | planned |
| 15 | Census TIGER/Line shapefiles | Geographic | planned |
| 16 | Census Geocoder API | Geographic | planned |
| 17 | Census of Governments | State/local | planned |
| 18 | Legistar | Local legislative | planned |
| 19 | Municode | Local legislative | planned |
| 20 | openstates/people | State executive | planned |
| 21 | Supreme Court Database (WashU) | Judicial | planned |
| 22 | PACER | Judicial | planned |
| 23 | NCSC Court Statistics Project | State judicial | planned |
| 24 | Senate LDA Lobbying API (lda.gov) | Federal legislative | planned — API access confirmed in hand |
| 25 | Congressional Financial Disclosures | Legislative/Judicial | planned |

## Canonical JSON outputs (24)

`members.json`, `votes.json`, `bills.json`, `campaign_finance.json`, `executive_officials.json`, `executive_actions.json`, `agencies.json`, `judges.json`, `opinions.json`, `spending.json`, `districts.json`, `scotus_cases.json`, `federal_cases.json`, `state_legislators.json`, `state_bills.json`, `state_executives.json`, `state_court_stats.json`, `state_districts.json`, `demographics.json`, `government_finances.json`, `local_legislation.json`, `local_officials.json`, `lobbying.json`, `financial_disclosures.json`, plus `pipeline_status.json`.

Field-level schemas per output carry over from the original planning docs unchanged; they're not reproduced here to avoid a second copy drifting out of sync — add them to the relevant Pydantic schema module as each output is actually built, since that's the version that has to be correct.

Note: `bills.json`, `executive_actions.json`, `opinions.json`, and `state_bills.json` originally specced a `summary_plain_english` field. That field is not being populated right now — see `AGENTS.md` → Current explicit boundaries. The schemas keep the field as nullable so it can be filled in later without a breaking migration.

## Repository layout

```
govmap.us/
├── backend/            # FastAPI app: pipelines, normalization, API
│   ├── Dockerfile      # migrations-on-start + uvicorn, non-root
│   ├── app/
│   │   ├── pipelines/  # one script per source, Layer 1
│   │   ├── normalize/  # one module per entity, Layer 2
│   │   ├── routers/    # API endpoints, Layer 3
│   │   ├── models/     # SQLAlchemy ORM models
│   │   ├── schemas/    # Pydantic validation/response models
│   │   ├── db.py
│   │   ├── config.py
│   │   └── main.py
│   ├── migrations/     # Alembic
│   └── data/staging/   # raw pipeline output, gitignored
├── frontend/           # Next.js app -- two zones, one deployment
│   ├── Dockerfile      # multi-stage, Next standalone output, non-root
│   ├── middleware.ts   # hostname routing: govmap.us vs app.govmap.us
│   ├── lib/
│   │   └── site-config.ts  # cross-zone URLs, GitHub, social/support links
│   ├── public/         # logo-dark.png, logo-light.png
│   └── app/
│       ├── page.tsx    # marketing site (govmap.us root)
│       ├── icon.png    # favicon (cropped Capitol mark)
│       └── app/        # the platform (app.govmap.us root, via rewrite)
│           ├── layout.tsx
│           ├── page.tsx
│           └── members/page.tsx
├── docker-compose.yml  # full stack: postgres + backend + frontend, loopback-bound
└── .github/workflows/  # CI (lint now, deploy once the runner exists)
```

## Phase checklist

Adapted from the original end-to-end plan, reordered to prove the pipeline contract on one source before fanning out — see the 2026-07-20 build log entry for why.

- [x] Repo scaffold, `.gitignore`, three canonical docs
- [ ] **Pilot**: `congress-legislators` pipeline → normalize → `members` table → `/api/members` → Next.js list page, running locally end-to-end
- [ ] Local dev loop verified (Postgres via `docker-compose`, backend, frontend all running together)
- [ ] CI: lint workflow green on push
- [ ] Fan out to remaining 24 source pipelines (Layer 1), reusing the pilot's pattern
- [ ] Normalization layer for all entities (Layer 2), `id_crosswalk` table populated
- [ ] All 24 JSON outputs live (Layer 3)
- [ ] FastAPI backend complete: all endpoints, Redis caching added *when needed*, APScheduler wiring
- [ ] Next.js frontend — Legislative branch complete
- [ ] Next.js frontend — Executive & Judicial branches
- [ ] Full cross-branch bill pipeline view
- [ ] Security hardening pass (rate limiting, CORS, dependency audit, load test)
- [ ] Self-hosted GitHub Actions runner + Tailscale deploy wired up
- [ ] Production launch on the home VM
- [ ] Post-launch: 30-day stability, then revisit LLM summarization with a real review process, then migrate to paid infrastructure once funded

## Known open items

- **PACER costs money per page**, not a flat quarterly fee — the pipeline needs to scope queries tightly and track spend, not just cap at "$30/qtr" and assume it holds.
- **OPM PLUM and White House scrapers are fragile by nature** (HTML scrapes with no API). They need to fail loudly on structural change, not silently return stale data — flagged in the original plan and still true.
- **Pipeline status resets on backend restart.** `pipeline_status.json` lives in the backend container's ephemeral filesystem (no volume — a named volume would hit the non-root-container permission trap), so `/internal/pipeline-status` returns 404 after a redeploy until the next scheduled/manual run. Member data itself is safe (Postgres volume); only the status file is transient.
- **Marketing site has no real social handles or support/donation link.** `frontend/lib/site-config.ts` ships with `socialLinks: []` and `supportUrl: null` on purpose rather than placeholder/fake links — fill them in as real accounts and a donation link exist.
- **Favicon is a stopgap crop**, not a designed icon mark — see README → *Sites & branding*. Fine for now, worth revisiting once there's a proper icon-only asset.
- **DNS not yet configured** for the `app.` subdomain split. `frontend/middleware.ts` assumes `app.govmap.us` resolves to the same deployment as `govmap.us` — that DNS record (and matching `cloudflared` routing) needs to exist before the split works in production.
