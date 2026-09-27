"""Live, query-time facts - solar/energy, bills due, and the media pipeline's download status.

Unlike ingest.py's static Home Knowledge (docs/hub/atlas, re-indexed every 6h - see the scheduled
HomeLab-AnvayaReindex task), these change by the minute and would be actively misleading if answered
from a stale snapshot, so they're fetched fresh on every matching question instead of ingested.

Each provider is independently optional and silent-by-default: a missing api_key/token/URL, or a live
call that fails, simply means that provider contributes nothing - it never turns into an error shown to
the user (the citation-enforcement fallback in answer.py already handles "found nothing" gracefully).
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional

import httpx

from .config import Settings


class LiveFact(NamedTuple):
    """A live_sources() result - retrieval.py turns this into its own Source (kept dependency-free of
    retrieval.py here to avoid a circular import: retrieval.py -> live_facts.py -> retrieval.py)."""
    plugin: str
    title: str
    uri: str
    text: str

_SOLAR_KEYWORDS = ("solar", "battery", "energy", "power", "consumption", "grid", "inverter", "kwh")
_BILLS_KEYWORDS = ("bill", "bills", "due", "payment", "invoice", "owe")
_MEDIA_KEYWORDS = ("movie", "movies", "torrent", "download", "downloading", "release",
                   "series", "episode", "show")

# Deye entities used by documentation/solar.html - see that file for the full sensor map.
_SOLAR_ENTITIES = {
    "today's solar production": "sensor.deye_station_32515_solar_generation_today_32515",
    "today's consumption": "sensor.deye_station_32515_daily_consumption_today_32515",
    "battery charge": "sensor.deye_station_32515_battery_state_of_charge_32515",
    "load right now": "sensor.deye_station_32515_load_power_32515",
}


def _matches(query: str, keywords: tuple[str, ...]) -> bool:
    # Word-boundary match, not raw substring - a substring check would false-positive e.g. "owe" inside
    # "power", or "bill" inside "billing" in a way that isn't actually about a bill.
    q = query.lower()
    return any(re.search(r"\b" + re.escape(k) + r"\b", q) for k in keywords)


async def _solar_fact(http: httpx.AsyncClient, s: Settings) -> Optional[str]:
    if not s.ha_token:
        return None
    headers = {"Authorization": f"Bearer {s.ha_token}"}
    parts = []
    try:
        for label, entity_id in _SOLAR_ENTITIES.items():
            r = await http.get(f"{s.ha_url}/api/states/{entity_id}", headers=headers, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            unit = (data.get("attributes") or {}).get("unit_of_measurement", "")
            parts.append(f"{label}: {data.get('state')}{unit}")
    except httpx.HTTPError:
        return None
    if not parts:
        return None
    return "Live solar/energy status (Home Assistant) - " + ", ".join(parts)


async def _bills_fact(http: httpx.AsyncClient, s: Settings) -> Optional[str]:
    try:
        r = await http.get(f"{s.finance_api_url}/api/bills", timeout=10)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    bills = r.json().get("bills", [])
    due = [b for b in bills if b.get("status") in ("past_due", "due_soon")]
    if not due:
        return "Live bills status (Finance OS) - nothing currently past due or due soon."
    lines = [f"{b.get('merchant', '?')}: ~{b.get('expected_median', '?')} due "
             f"{str(b.get('next_expected', '?'))[:10]} ({b.get('status')})" for b in due[:5]]
    return "Live bills due (Finance OS) - " + "; ".join(lines)


async def _queue_fact(http: httpx.AsyncClient, url: str, api_key: str, label: str) -> Optional[str]:
    if not api_key:
        return None
    try:
        r = await http.get(f"{url}/api/v3/queue", headers={"X-Api-Key": api_key}, timeout=10)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    records = r.json().get("records", [])
    if not records:
        return None
    items = "; ".join(f"{rec.get('title', '?')} ({rec.get('trackedDownloadState', rec.get('status', '?'))})"
                       for rec in records[:5])
    return f"{label} downloading now: {items}"


async def _media_fact(http: httpx.AsyncClient, s: Settings) -> Optional[str]:
    movies = await _queue_fact(http, s.radarr_url, s.radarr_api_key, "Movies")
    shows = await _queue_fact(http, s.sonarr_url, s.sonarr_api_key, "Episodes")
    parts = [p for p in (movies, shows) if p]
    if not parts:
        return "Live media pipeline status (Radarr/Sonarr) - nothing is currently downloading."
    return "Live media pipeline status (Radarr/Sonarr) - " + " | ".join(parts)


async def live_sources(query: str, settings: Settings, classes: set[str], *,
                        transport: Optional[httpx.AsyncBaseTransport] = None) -> list[LiveFact]:
    """Query-time facts that supplement (never replace) Home Knowledge's static doc search - see retrieve()
    in retrieval.py, which turns each of these into its own numbered Source, merged in before the doc hits.
    `classes` is the same scope+profile permission set retrieve() already computed (allowed_classes()):
    bills counts as `finance` (never for Family, matching every other finance-class document), solar/media
    count as `household`.
    """
    facts: list[LiveFact] = []
    async with httpx.AsyncClient(transport=transport) as http:
        if "household" in classes and _matches(query, _SOLAR_KEYWORDS):
            text = await _solar_fact(http, settings)
            if text:
                facts.append(LiveFact("live.solar", "Live solar/energy status", "/solar.html", text))
        if "finance" in classes and _matches(query, _BILLS_KEYWORDS):
            text = await _bills_fact(http, settings)
            if text:
                facts.append(LiveFact("live.finance", "Live bills status", "/finance/", text))
        if "household" in classes and _matches(query, _MEDIA_KEYWORDS):
            # _media_fact always returns a string (falls back to "nothing is downloading"), unlike solar/bills
            # which can genuinely have nothing to say (e.g. no credentials configured at all).
            text = await _media_fact(http, settings)
            facts.append(LiveFact("live.media", "Live media pipeline status", "/arrivals.html", text))
    return facts
