"""
orbitval/orbits/tle.py

Celestrak TLE fetcher and cache for OrbitVal.
Supports live fetch, local cache, and offline/manual TLE input.

ADR-003: Celestrak is the primary TLE source.
Correct endpoint: celestrak.org/NORAD/elements/gp.php
Fallback: Space-Track.org or direct TLE string input.
"""

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta
import json
import urllib.request
import urllib.parse
import urllib.error
from orbitval.logging import get_logger
log = get_logger("tle")

CELESTRAK_GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
CACHE_DIR = Path.home() / ".orbitval" / "tle_cache"
CACHE_EXPIRY_HOURS = 6


@dataclass
class TLERecord:
    """A single TLE record with metadata."""
    name: str
    line1: str
    line2: str
    fetched_at: str  # ISO 8601


def _cache_path(satellite_name: str) -> Path:
    """Return the cache file path for a given satellite name."""
    safe_name = satellite_name.strip().replace(" ", "_").upper()
    safe_name = safe_name.replace("(", "").replace(")", "")
    return CACHE_DIR / f"{safe_name}.json"


def _is_cache_fresh(cache_file: Path) -> bool:
    """Check if cached TLE is still within expiry window."""
    if not cache_file.exists():
        return False
    try:
        data = json.loads(cache_file.read_text())
        fetched = datetime.fromisoformat(data["fetched_at"])
        return datetime.utcnow() - fetched < timedelta(hours=CACHE_EXPIRY_HOURS)
    except Exception:
        return False


def _read_cache(cache_file: Path) -> TLERecord:
    """Read a TLE record from cache."""
    data = json.loads(cache_file.read_text())
    return TLERecord(
        name=data["name"],
        line1=data["line1"],
        line2=data["line2"],
        fetched_at=data["fetched_at"],
    )


def _write_cache(cache_file: Path, record: TLERecord) -> None:
    """Write a TLE record to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({
        "name": record.name,
        "line1": record.line1,
        "line2": record.line2,
        "fetched_at": record.fetched_at,
    }))


def fetch_tle(satellite_name: str) -> TLERecord:
    """
    Fetch a TLE for a named satellite from Celestrak.
    Uses cache if fresh, otherwise fetches live.

    Args:
        satellite_name: common name e.g. "ISS (ZARYA)", "TERRA"

    Returns:
        TLERecord with line1, line2, and fetch timestamp

    Raises:
        ValueError: if satellite not found
        ConnectionError: if fetch fails and no cache available
    """
    cache_file = _cache_path(satellite_name)

    # Return cached version if still fresh
    if _is_cache_fresh(cache_file):
        log.info("Cache hit for '%s'", satellite_name)
        return _read_cache(cache_file)

    # Fetch from Celestrak using the correct GP endpoint
    try:
        params = urllib.parse.urlencode({
            "NAME": satellite_name.strip(),
            "FORMAT": "TLE",
        })
        url = f"{CELESTRAK_GP_URL}?{params}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "OrbitVal/1.0.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8").strip()

        if not raw or raw == "No GP data found":
            raise ValueError(
                f"Satellite '{satellite_name}' not found on Celestrak. "
                f"Check the name matches exactly (e.g. 'ISS (ZARYA)')."
            )

        lines = [l.strip() for l in raw.splitlines() if l.strip()]

        if len(lines) < 3:
            raise ValueError(
                f"Unexpected response for '{satellite_name}': {raw[:100]}"
            )

        record = TLERecord(
            name=lines[0],
            line1=lines[1],
            line2=lines[2],
            fetched_at=datetime.utcnow().isoformat(),
        )
        _write_cache(cache_file, record)
        return record

    except urllib.error.URLError as e:
        # Network failed — fall back to stale cache if available
        if cache_file.exists():
            log.warning(
                "Could not reach Celestrak (%s). Using stale cache for '%s'",e, satellite_name
            )
            return _read_cache(cache_file)
        raise ConnectionError(
            f"Could not fetch TLE for '{satellite_name}' "
            f"and no cache available. "
            f"Provide TLE strings directly or check your connection."
        ) from e


def tle_from_strings(name: str, line1: str, line2: str) -> TLERecord:
    """
    Create a TLERecord directly from strings.
    Use this for offline/air-gapped operation or manual TLE input.

    Args:
        name: satellite name
        line1: TLE line 1
        line2: TLE line 2

    Returns:
        TLERecord (not cached)
    """
    return TLERecord(
        name=name,
        line1=line1,
        line2=line2,
        fetched_at=datetime.utcnow().isoformat(),
    )