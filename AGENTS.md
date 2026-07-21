# AGENTS.md

Rules for anyone — human or AI — writing code in this repository. This is the only document in this repo that discusses coding-agent workflow; keep it that way. If you're looking for what GovMap *is*, read [README.md](README.md). If you're looking for what's been built and what's next, read [CODE-MANIFEST.md](CODE-MANIFEST.md).

## Coding agent division of labor

This project uses two AI coding tools deliberately, not interchangeably:

| Tool | Owns | Because |
| --- | --- | --- |
| **Gemini Code Assist** | Repo/service scaffolding, boilerplate CRUD endpoints against an already-defined schema, mechanical source pipelines that repeat a proven pattern, CI workflow YAML, config files | High-volume, low-risk, pattern-following work. Cheap iteration, save Claude's compute for what actually needs judgment. |
| **Claude Code** | Architecture decisions, the normalization/ID-crosswalk layer, the cross-branch bill pipeline connector, fragile scrapers, database schema/migrations, and a security review pass on everything before it merges — regardless of which tool wrote it | This is where subtle bugs hide and where a mistake is expensive: wrong joins silently corrupt data, wrong auth silently exposes it. |

Both tools follow the rules below. Neither tool merges its own code without the review step in **Security & review gate**.

## Non-negotiable normalization rules

These are architectural law, not style preferences. Every pipeline and every normalizer follows them from the first line of code — retrofitting them later has already been identified as expensive.

- **Bioguide ID** is the master key for every federal legislative person record. If a source doesn't provide one and there's no clean mapping to it, that's a `CODE-MANIFEST.md` entry before another line of code is written for that source.
- **OCD ID** is the equivalent master key for state and local person/jurisdiction records. Federal uses Bioguide, state/local uses OCD — never invent a third ID system to paper over the gap between them.
- **FIPS code** is the primary key for every geographic table. Every geographic join across sources runs through it.
- **CGAC code** joins the Executive branch org chart (`agencies`) to spending data (`spending`). Store it on both sides of that join or the accountability chain breaks.
- **ISO 8601** for every date, everywhere, enforced in the normalization layer via a single shared `normalize_date()` utility — never store a raw source date string in the database. Sources return dates in inconsistent formats; reconciling that after the fact is how you get silently broken date-range queries.
- **CRP industry codes and NAICS codes are never joined to each other.** They're different taxonomies for different things (campaign donors vs. federal contracts). Label each with its source taxonomy in the UI and keep them separate in the schema.
- **FEC candidate IDs are stored as an array** (`fec_candidate_ids[]`), not a single value — members generate new IDs across election cycles.
- **Cross-source ID matches that aren't backed by a shared identifier** (e.g., a judge who was previously a member of Congress, matched by name + date) **must be documented** in the `id_crosswalk` notes as a manual correction, not silently assumed correct.

## Pipeline contract

Every data source follows the same three layers. Don't collapse them, even for a "simple" source:

1. **Pipeline script** (`backend/app/pipelines/<source>.py`) — pulls from exactly one source, handles that source's auth/pagination/rate limits, validates the raw shape with a Pydantic model, writes staging JSON, updates `pipeline_status.json` with timestamp/record count/status. Fails loudly (raises, logs) on unexpected shape — never silently emits stale or partial data.
2. **Normalizer** (`backend/app/normalize/<entity>.py`) — reads staging JSON, applies the ID crosswalk and the rules above, upserts into Postgres via SQLAlchemy.
3. **API/output** (`backend/app/routers/<entity>.py`) — reads from Postgres, serves the canonical JSON shape defined for that entity.

## Security & review gate

- Secrets live in environment variables only, loaded via `.env` locally (never committed — see `.gitignore`). Zero API keys, tokens, or credentials in code or commit history, ever.
- No raw string interpolation into SQL, anywhere. All database access goes through the SQLAlchemy ORM.
- Every external input (query params, path params, request bodies) is validated with a Pydantic model before it touches business logic.
- Any endpoint that isn't meant to be public (e.g. `/internal/*`) must be access-controlled before it's deployed anywhere reachable outside localhost — don't ship an unauthenticated internal endpoint to the tunnel and call it done.
- Before code — from either tool — merges to `main`, it gets a review pass against this checklist. Gemini-authored scaffolding is not exempt.

## Current explicit boundaries

Things that are deliberately **not** being built right now. Don't scaffold them "for later" — that's premature and it's the kind of half-finished surface area this project is trying to avoid.

- **No LLM summarization.** `llm_summarizer.py`, `summary_plain_english` fields, the neutrality self-scoring classifier, and the human review queue are on hold. GovMap ships raw, sourced government data only until there's a review process that can keep pace with volume. Do not populate summary fields with placeholder or unreviewed model output.
- **No Redis / caching layer.** It's in the target tech stack but isn't wired into anything yet. Add it when a specific endpoint demonstrably needs it, not speculatively.
- **No auth/user accounts yet.** Don't scaffold login, sessions, or user tables ahead of an actual feature that needs them.

## Conventions

- **Python**: `ruff` for lint + format, type hints on all function signatures, Pydantic v2 for all data validation, `async` SQLAlchemy for all DB access.
- **TypeScript**: `eslint` + `tsc --noEmit` must pass; no `any` without a comment explaining why it's unavoidable.
- **Commits**: describe the *why*, not a restatement of the diff. No agent-attribution boilerplate beyond what the tool itself appends.
- **Every new source pipeline** ships with: the pipeline script, the normalizer, a schema update/migration if needed, and a `CODE-MANIFEST.md` entry — not just the script.
