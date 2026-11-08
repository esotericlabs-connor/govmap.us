"""Public bug-report endpoint → appends to bug_reports.log.

`POST /api/report` takes a category/subcategory (validated against a fixed
allowlist, so those fields can never be an injection vector), a free-text
message, and the page URL. All free text is scrubbed — HTML/angle-brackets and
control characters stripped, token-like strings redacted, length-capped — before
being appended as one plain-text block to `<log_dir>/bug_reports.log`. That file
is never rendered as HTML, so reports are XSS-safe by construction; stripping
newlines also prevents forged/injected log entries.

Lightly hardened against abuse (it's public): a per-IP rate limit, a payload
cap (Pydantic max_length), and an Origin/Referer check against the configured
origins.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections import deque
from datetime import UTC, datetime
from ipaddress import ip_address
from urllib.parse import urlsplit

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.report_categories import REPORT_CATEGORIES, normalize

logger = logging.getLogger("app.routers.report")

router = APIRouter(prefix="/api", tags=["report"])

_BUG_LOG = "bug_reports.log"
_MSG_MAX = 2000
_URL_MAX = 300
_UA_MAX = 300

# Best-effort in-memory per-IP rate limit (resets on restart).
_RATE_WINDOW = 3600  # seconds
_RATE_MAX = 20       # reports per IP per window
_GLOBAL_RATE_MAX = 200
_MAX_RATE_IPS = 10000
_rate: dict[str, deque[float]] = {}
_global_rate: deque[float] = deque()

_TAG_RE = re.compile(r"<[^>]*>")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]+")     # includes \r \n \t — collapse to space
_SECRET_RE = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")  # redact long token-like strings


class ReportIn(BaseModel):
    category: str = Field(default="Other", max_length=40)
    subcategory: str = Field(default="Other", max_length=60)
    message: str = Field(min_length=1, max_length=5000)
    url: str = Field(default="", max_length=500)
    turnstile_token: str | None = Field(default=None, max_length=2048)


def _scrub(text: str, max_len: int) -> str:
    """Make user text safe to store as one plain-text line: drop tags + angle
    brackets, collapse control chars/newlines to spaces (blocks log injection),
    redact token-like strings, and cap length."""
    text = _TAG_RE.sub(" ", text)
    text = text.replace("<", " ").replace(">", " ")
    text = _CTRL_RE.sub(" ", text)
    text = _SECRET_RE.sub("[redacted]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _scrub_url(url: str) -> str:
    url = url.split("?", 1)[0].split("#", 1)[0]  # drop query/fragment (possible tokens)
    return _scrub(url, _URL_MAX)


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        peer_ip = ip_address(peer)
    except ValueError:
        return "unknown"
    if any(peer_ip in network for network in settings.trusted_proxy_networks):
        forwarded = request.headers.get("cf-connecting-ip")
        if forwarded:
            try:
                return str(ip_address(forwarded.strip()))
            except ValueError:
                logger.warning("ignoring malformed client IP from trusted proxy")
    return str(peer_ip)


def _rate_ok(ip: str) -> bool:
    now = time.monotonic()
    while _global_rate and now - _global_rate[0] >= _RATE_WINDOW:
        _global_rate.popleft()
    if len(_global_rate) >= _GLOBAL_RATE_MAX:
        return False
    if ip not in _rate and len(_rate) >= _MAX_RATE_IPS:
        expired = [key for key, times in _rate.items() if now - times[-1] >= _RATE_WINDOW]
        for key in expired:
            del _rate[key]
        if len(_rate) >= _MAX_RATE_IPS:
            return False
    recent = _rate.setdefault(ip, deque())
    while recent and now - recent[0] >= _RATE_WINDOW:
        recent.popleft()
    if len(recent) >= _RATE_MAX:
        return False
    recent.append(now)
    _global_rate.append(now)
    return True


def _origin(url: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        port = parsed.port
        return parsed.scheme, parsed.hostname, port if port is not None else (
            443 if parsed.scheme == "https" else 80
        )
    except ValueError:
        return None


def _origin_ok(request: Request) -> bool:
    allowed = settings.cors_origin_list
    if not allowed:
        return True  # origins unset (dev) — don't block
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    incoming = _origin(origin)
    return incoming is not None and any(incoming == _origin(a) for a in allowed)


_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _verify_turnstile(token: str | None, ip: str) -> bool:
    """Cloudflare Turnstile check. Disabled (always allow) unless
    TURNSTILE_SECRET_KEY is set; once set, a valid token is required. Fails
    *closed* on a missing token or an explicit rejection (a bot), but *open* on a
    network error reaching Cloudflare so a CF outage can't lock out real users
    (the origin + rate limits still apply)."""
    secret = os.getenv("TURNSTILE_SECRET_KEY", "").strip()
    if not secret:
        return True
    if not token:
        return False
    try:
        resp = requests.post(
            _TURNSTILE_VERIFY_URL,
            data={"secret": secret, "response": token, "remoteip": ip},
            timeout=10,
        )
        return bool(resp.json().get("success"))
    except Exception as exc:  # noqa: BLE001 — network/parse error must not lock out users
        logger.warning("turnstile verify unreachable, allowing: %s", exc)
        return True


def _append(block: str) -> None:
    os.makedirs(settings.log_dir, exist_ok=True)
    with open(os.path.join(settings.log_dir, _BUG_LOG), "a", encoding="utf-8") as fh:
        fh.write(block)


@router.post("/report")
async def submit_report(payload: ReportIn, request: Request) -> dict:
    ip = _client_ip(request)
    if not _origin_ok(request):
        raise HTTPException(status_code=403, detail="forbidden")
    if not _rate_ok(ip):
        raise HTTPException(status_code=429, detail="too many reports; try again later")
    if not await asyncio.to_thread(_verify_turnstile, payload.turnstile_token, ip):
        raise HTTPException(status_code=403, detail="verification failed — please retry")

    category, subcategory = normalize(payload.category, payload.subcategory)
    message = _scrub(payload.message, _MSG_MAX)
    if not message:
        raise HTTPException(status_code=422, detail="message is empty after sanitizing")
    url = _scrub_url(payload.url)
    ua = _scrub(request.headers.get("user-agent", ""), _UA_MAX)
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    block = (
        "────────────────────────────────────────\n"
        f"{ts}  [{category} / {subcategory}]\n"
        f"URL: {url or '(none)'}\n"
        f"UA:  {ua or '(none)'}\n"
        f"Msg: {message}\n"
    )
    try:
        await asyncio.to_thread(_append, block)
    except OSError as exc:
        logger.warning("bug report could not be written: %s", exc)
        raise HTTPException(status_code=503, detail="could not record report") from exc

    logger.info("bug report filed [%s / %s]", category, subcategory)
    return {"ok": True}


@router.get("/report/categories")
async def report_categories() -> dict:
    """The category → subcategory allowlist, so the frontend form always matches
    the server's validation (also hard-coded in lib/report-categories.ts)."""
    return REPORT_CATEGORIES
