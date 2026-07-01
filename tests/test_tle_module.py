"""
tests/test_tle_module.py

Unit tests for orbitval/orbits/tle.py — cache logic, tle_from_strings,
and fetch_tle failure modes. All network calls are mocked.
"""

import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbitval.orbits.tle import (
    tle_from_strings,
    fetch_tle,
    _is_cache_fresh,
    _read_cache,
    _write_cache,
    _cache_path,
    TLERecord,
)

TLE1 = "1 25544U 98067A   24001.50000000  .00001000  00000+0  10000-4 0  9991"
TLE2 = "2 25544  51.6400 100.0000 0001000  90.0000 270.0000 15.50000000000010"


class TestTleFromStrings:
    def test_preserves_name(self):
        r = tle_from_strings("MY-SAT", TLE1, TLE2)
        assert r.name == "MY-SAT"

    def test_preserves_line1(self):
        r = tle_from_strings("MY-SAT", TLE1, TLE2)
        assert r.line1 == TLE1

    def test_preserves_line2(self):
        r = tle_from_strings("MY-SAT", TLE1, TLE2)
        assert r.line2 == TLE2

    def test_returns_tle_record(self):
        r = tle_from_strings("X", TLE1, TLE2)
        assert isinstance(r, TLERecord)

    def test_fetched_at_is_set(self):
        r = tle_from_strings("X", TLE1, TLE2)
        assert r.fetched_at  # non-empty string


class TestCacheFreshness:
    def test_missing_file_is_not_fresh(self, tmp_path):
        assert not _is_cache_fresh(tmp_path / "nonexistent.json")

    def test_stale_cache_is_not_fresh(self, tmp_path):
        cache = tmp_path / "tle.json"
        stale_time = (datetime.utcnow() - timedelta(hours=25)).isoformat()
        cache.write_text(json.dumps({
            "name": "ISS", "line1": TLE1, "line2": TLE2,
            "fetched_at": stale_time,
        }))
        assert not _is_cache_fresh(cache)

    def test_fresh_cache_is_fresh(self, tmp_path):
        cache = tmp_path / "tle.json"
        fresh_time = datetime.utcnow().isoformat()
        cache.write_text(json.dumps({
            "name": "ISS", "line1": TLE1, "line2": TLE2,
            "fetched_at": fresh_time,
        }))
        assert _is_cache_fresh(cache)

    def test_corrupt_cache_is_not_fresh(self, tmp_path):
        cache = tmp_path / "tle.json"
        cache.write_text("this is not json {{{{")
        assert not _is_cache_fresh(cache)


class TestFetchTleCache:
    def test_cache_hit_skips_network(self, tmp_path):
        """A fresh cache entry must be returned without any HTTP call."""
        fresh_time = datetime.utcnow().isoformat()
        cache_data = json.dumps({
            "name": "ISS (ZARYA)", "line1": TLE1, "line2": TLE2,
            "fetched_at": fresh_time,
        })
        with patch("orbitval.orbits.tle._cache_path") as mock_path, \
             patch("orbitval.orbits.tle._is_cache_fresh", return_value=True), \
             patch("orbitval.orbits.tle._read_cache") as mock_read, \
             patch("orbitval.orbits.tle.urllib.request.urlopen") as mock_urlopen:
            mock_read.return_value = TLERecord(
                name="ISS (ZARYA)", line1=TLE1, line2=TLE2, fetched_at=fresh_time
            )
            result = fetch_tle("ISS (ZARYA)")
            mock_urlopen.assert_not_called()
        assert result.line1 == TLE1

    def test_network_failure_no_cache_raises_connection_error(self):
        """When fetch fails and no cache exists, ConnectionError is raised."""
        import urllib.error
        with patch("orbitval.orbits.tle._is_cache_fresh", return_value=False), \
             patch("orbitval.orbits.tle._cache_path") as mock_path, \
             patch("orbitval.orbits.tle.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("network down")):
            mock_path.return_value = Path("/nonexistent/cache.json")
            with pytest.raises(ConnectionError):
                fetch_tle("ISS (ZARYA)")

    def test_satellite_not_found_raises_value_error(self):
        """Empty response body (sat not in Celestrak) should raise ValueError."""
        mock_response = MagicMock()
        mock_response.read.return_value = b""
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("orbitval.orbits.tle._is_cache_fresh", return_value=False), \
             patch("orbitval.orbits.tle._cache_path") as mock_path, \
             patch("orbitval.orbits.tle.urllib.request.urlopen",
                   return_value=mock_response):
            mock_path.return_value = Path("/nonexistent/cache.json")
            with pytest.raises((ValueError, ConnectionError)):
                fetch_tle("DOES-NOT-EXIST-XYZ")
