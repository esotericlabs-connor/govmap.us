# GovMap.us

<img width="975" height="283" alt="image" src="https://github.com/user-attachments/assets/75e24029-21c9-4501-9e41-4b97de882381" />

<img width="975" height="283" alt="image" src="https://github.com/user-attachments/assets/cb86aa69-3cde-4e54-b2e0-44500704efd0" />


A mobile-first web app that makes the entire US federal government easy to understand for everyday Americans. GovMap presents real, verified, public data — who represents you, how they vote, who runs the agencies that govern you, where the money goes, and how a bill moves from introduction through signing through judicial challenge — in a clean, digestible format, extended to the full process of American government.


> From City Council to Congress.

**Status:** pre-launch, single-pipeline proof of concept. See [CODE-MANIFEST.md](CODE-MANIFEST.md) for the current build log and phase checklist.

## Mission

Apathy is largely a UX problem. - Govmap.us aims to be a modern, nonpartisan, transparent civic tool that gives every American a clear, real-time view of their entire federal government — who represents them, how they vote, who runs the agencies that govern them, where the money goes, and how laws move through all three branches.

## Critical design principles

- **Nonpartisan above all else** — the moment it looks politically aligned, half the users are gone. 
- **Data only** — no editorializing, no spin. Let the records speak. Every published fact links back to its official source.
- **Plain English** — no legal, legislative, or bureaucratic jargon anywhere in the UI.
- **Mobile-first** — most users will discover and use this on their phone.
- **Open methodology** — how data is sourced, normalized, and displayed is documented publicly so it cannot be credibly called biased.
- **All three branches** — Legislative, Executive, and Judicial are treated as equal pillars of the product.

## Scope

| Branch | What it covers | Update cadence |
| --- | --- | --- |
| Legislative | 535 members of Congress, bills, votes, committees, campaign finance, lobbying | Every 30 min in session, daily otherwise |
| Executive | President, VP, Cabinet, 15 departments, agency heads, executive orders | Weekly sync + daily Federal Register feed |
| Judicial | 9 SCOTUS justices, 179 circuit judges, 677 district judges, opinions | As opinions are published |

State and local layers (state legislatures, governors, city councils, state courts) extend the same model once the federal build is stable. Full source list, cadences, and JSON output contracts are in [CODE-MANIFEST.md](CODE-MANIFEST.md).

The product's signature feature is the **full bill pipeline**: a single timeline connecting a bill's introduction (Congress.gov) through signature or veto (Federal Register) through any judicial challenge (CourtListener). No other civic tool currently connects all three stages in one view.

## Where things stand right now

The project is deliberately being proven on a **narrow, real slice** before it's widened: one data source, pulled and validated, normalized into Postgres, served over a REST API, and rendered in a minimal web UI. Everything else in the five-pillar plan gets added only after that loop is demonstrated to work reliably.

Two things are intentionally **on hold**, not forgotten:

- **LLM/plain-English summarization** — the AI/LLM feature set (bill summaries, EO summaries, opinion summaries, natural-language search) is deferred. GovMap ships with raw, sourced data only until there's a human review process that can actually keep pace with it. See [AGENTS.md](AGENTS.md) for the current boundary.
- **Caching (Redis)** — not wired in yet. It gets added when an endpoint actually needs it, not before.

## Data approach

Every pipeline follows the same three-layer contract:

1. **Source pipeline** — one script per source, isolated. Pull, handle that source's auth/pagination/rate limits, validate shape, write raw staging JSON, record the run in `pipeline_status.json`.
2. **Normalization** — map raw fields to the canonical schema, resolve cross-source IDs (Bioguide ID for federal legislative people, OCD ID for state/local, FIPS for geography, CGAC for agencies), enforce ISO 8601 on every date, write to Postgres.
3. **JSON output** — a database query serialized to the canonical output file/endpoint, consumed by the frontend.

Nothing skips a layer. The full identifier and normalization rules are non-negotiable and documented in [AGENTS.md](AGENTS.md).

## Tech stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.11+, FastAPI, SQLAlchemy (async), Alembic |
| Database | PostgreSQL |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS |
| Pipelines | Python scripts, one per source, scheduled via APScheduler |
| Infrastructure | Self-hosted Linux VM, tunneled via Cloudflare (`cloudflared`), no exposed ports; Tailscale-only SSH management; GitHub Actions for CI/CD |

The VM is a deliberate low-cost choice for the pre-funding stage — uptime is being knowingly traded for near-zero hosting cost. The plan is to move to paid infrastructure (and a managed Postgres instance) once the project has funding.

## Sites & branding

GovMap is one Next.js deployment serving two logical zones, split by `frontend/middleware.ts` on hostname:

- **govmap.us** — the marketing site (`frontend/app/page.tsx`): what GovMap is, why it exists, and a way in.
- **app.govmap.us** — the platform itself (`frontend/app/app/`): the actual product.

The "Enter GovMap" button on the marketing site crosses from one host to the other, so it's the one link in the frontend that has to be an absolute URL rather than a relative path — see `frontend/lib/site-config.ts`, the single place cross-zone URLs, the GitHub link, and (once they exist) social handles and a support link are defined.

Brand assets live in `frontend/public/` (`logo-dark.png`, `logo-light.png` — full lockups with an opaque background baked in, meant for full-bleed placement, not floating over an arbitrary background color). The favicon (`frontend/app/icon.png`) is a square crop of just the Capitol mark from the dark logo, generated because no standalone icon-only asset existed yet — a proper source mark would give a cleaner result and is a fine thing to swap in later.

**Open:** `siteConfig.socialLinks` and `contactEmail` are intentionally empty — nothing fake is linked until real accounts exist. `supportLinks` holds the six live donation platforms shown on the landing page; the landing page also carries a "seeking a fiscal sponsor" note.

## Local development

Prerequisites: Python 3.11+, Node.js 20+, and Docker (for local Postgres — or point `DATABASE_URL` at any Postgres 16 instance).

```bash
# 1. Start Postgres
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python -m app.pipelines.congress_legislators   # pull + validate + stage
python -m app.normalize.members                # normalize + load into Postgres
uvicorn app.main:app --reload                  # http://localhost:8000

# 3. Frontend (separate terminal)
cd frontend
cp .env.example .env.local
npm install
npm run dev                                    # marketing: http://localhost:3000
                                                 # platform:  http://app.localhost:3000
```

`*.localhost` resolves to loopback with no hosts-file editing needed, so `app.localhost:3000` exercises the exact same middleware-based host routing as `app.govmap.us` will in production. Visit `http://app.localhost:3000/members` — it should list all current members of Congress, pulled live from the `unitedstates/congress-legislators` GitHub repo, normalized, and served through the API.

## Production deployment

Production runs the whole stack in Docker on the Ubuntu VM — `postgres`, `backend`, `frontend`, and `cloudflared` — reached only through a Cloudflare Tunnel (no public inbound ports). Everything is driven by one script:

```bash
cd /opt/govmap && bash scripts/deploy.sh
```

`scripts/deploy.sh` is the single deploy path (used by hand and by the GitHub Actions runner): it prereq-checks the box, syncs to `origin/main`, builds, brings up all four containers, runs migrations, refreshes data, and prints a health check. `--no-data` skips the data refresh for code-only changes.

### The one piece of per-box state: `.env`

Everything else lives in the repo or in Cloudflare. The server's `/opt/govmap/.env` (gitignored) holds just:

- `POSTGRES_PASSWORD` — the DB password. `deploy.sh` generates one if `.env` is absent.
- `CLOUDFLARE_TUNNEL_TOKEN` — connects the `cloudflared` container to the tunnel. Without it the stack runs but the public site stays down.
- `INTERNAL_USER` / `INTERNAL_PASSWORD` — optional, unlock the `/internal/*` ops endpoints.

See [.env.example](.env.example) for the template. **Back this file up somewhere safe (a password manager)** — restoring it is what makes a rebuild instant.

### Rebuilding on a fresh box

Because the tunnel is **dashboard-managed**, its routes (`govmap.us` → `frontend:3000`, `api.govmap.us` → `backend:8000`, `app.govmap.us` → `frontend:3000`) live in Cloudflare and survive any rebuild. Reconnecting is just restoring the token:

```bash
sudo mkdir -p /opt/govmap && sudo chown "$USER":"$USER" /opt/govmap
git clone https://github.com/esotericlabs-connor/govmap.us.git /opt/govmap   # no sudo — user must own it
cd /opt/govmap
cp .env.example .env && chmod 600 .env          # then fill in POSTGRES_PASSWORD + CLOUDFLARE_TUNNEL_TOKEN
bash scripts/deploy.sh
```

That's it — the connector attaches to the **same** tunnel, the routes are already there, and govmap.us is live. Nothing to reconfigure in Cloudflare.

**If you ever lose the token:** get a fresh one from the Cloudflare dashboard → the `govmap` tunnel → connector install command (the `eyJ…` after `--token`), or **Rotate token**. The tunnel itself (ID `ebdeb681-961d-4321-8beb-2f14b35c6143`) and its routes stay put; only the token changes. Update `.env` and redeploy.

Server hardening (UFW, Tailscale, fail2ban, nightly `pg_dump` backups) is separate host setup — see [CODE-MANIFEST.md](CODE-MANIFEST.md).

## Documentation

Only three documents explain and govern this project:

- **README.md** (this file) — what GovMap is.
- **[CODE-MANIFEST.md](CODE-MANIFEST.md)** — what's been built, in what order, and what's next.
- **[AGENTS.md](AGENTS.md)** — the rules coding agents (human or AI) follow when working in this repo.

## License

GPLv3 — see [LICENSE](LICENSE). GovMap is a nonprofit, nonpartisan civic tool supported by donations and grants, not advertising or political funding.
