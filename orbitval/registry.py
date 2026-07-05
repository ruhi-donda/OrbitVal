"""
orbitval/registry.py

Append-only hash registry for ORF report attestation.

Local implementation of the Certificate Transparency model described
in ARCHITECTURE.md under "Hash registry design": every generated
report's test_integrity_hash is appended to a JSONL log that is never
edited or deleted. Each entry carries the SHA-256 hash of the previous
entry's serialized line, so altering, reordering, or removing any past
entry breaks the chain for everything after it.

Scope: this proves provenance against local history only. It does NOT
prevent someone from deleting or replacing the entire registry file —
that requires a hosted/remote registry (future work, see
ARCHITECTURE.md).

Registry path resolution (first match wins):
1. explicit path argument
2. ORBITVAL_REGISTRY environment variable
3. .orbitval/registry.jsonl in the current working directory
"""

import json
import os
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# prev_entry_hash of the first entry in the chain
GENESIS_HASH = "0" * 64

REGISTRY_ENV_VAR = "ORBITVAL_REGISTRY"
DEFAULT_REGISTRY_PATH = Path(".orbitval") / "registry.jsonl"


def resolve_registry_path(path: str | Path | None = None) -> Path:
    """Resolve the registry file path: explicit arg > env var > default."""
    if path is not None:
        return Path(path)
    env = os.environ.get(REGISTRY_ENV_VAR)
    if env:
        return Path(env)
    return DEFAULT_REGISTRY_PATH


def _serialize_entry(entry: dict) -> str:
    """Canonical single-line serialization of an entry."""
    return json.dumps(entry, sort_keys=True, separators=(",", ":"))


def _hash_line(line: str) -> str:
    """SHA-256 of an entry line exactly as stored (no trailing newline)."""
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def _read_lines(path: Path) -> list[str]:
    """Read non-empty entry lines from the registry file."""
    if not path.exists():
        return []
    return [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def append_entry(
    report_hash: str,
    satellite_id: str,
    registry_path: str | Path | None = None,
) -> dict:
    """
    Append a new entry to the registry after report generation.

    The entry is chained to the previous one via prev_entry_hash
    (SHA-256 of the previous entry's line). The file is only ever
    opened in append mode — existing lines are never rewritten.

    Returns:
        The entry dict that was appended.
    """
    path = resolve_registry_path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = _read_lines(path)
    prev_hash = _hash_line(lines[-1]) if lines else GENESIS_HASH

    entry = {
        "report_hash": report_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "satellite_id": satellite_id,
        "prev_entry_hash": prev_hash,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(_serialize_entry(entry) + "\n")
    return entry


@dataclass
class ChainVerification:
    """Result of walking the full registry chain."""
    ok: bool
    entry_count: int
    error: str | None = None
    broken_at: int | None = None  # 0-based index of first bad entry


def verify_chain(registry_path: str | Path | None = None) -> ChainVerification:
    """
    Verify the full chain integrity of the registry.

    Walks every entry in order and confirms each prev_entry_hash
    matches the hash of the previous entry's line (GENESIS_HASH for
    the first entry). A missing or empty registry is a trivially
    intact chain of zero entries.
    """
    path = resolve_registry_path(registry_path)
    lines = _read_lines(path)

    expected_prev = GENESIS_HASH
    for i, line in enumerate(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            return ChainVerification(
                ok=False, entry_count=len(lines), broken_at=i,
                error=f"entry {i} is not valid JSON",
            )
        if not isinstance(entry, dict) or "prev_entry_hash" not in entry:
            return ChainVerification(
                ok=False, entry_count=len(lines), broken_at=i,
                error=f"entry {i} is missing prev_entry_hash",
            )
        if entry["prev_entry_hash"] != expected_prev:
            return ChainVerification(
                ok=False, entry_count=len(lines), broken_at=i,
                error=(
                    f"entry {i} prev_entry_hash does not match hash of "
                    f"entry {i - 1}" if i else
                    f"entry {i} prev_entry_hash is not the genesis hash"
                ),
            )
        expected_prev = _hash_line(line)

    return ChainVerification(ok=True, entry_count=len(lines))


def check_provenance(
    report_hash: str,
    registry_path: str | Path | None = None,
) -> tuple[str, dict | None]:
    """
    Look up a report hash in the registry.

    Verifies the full chain first — a registry tampered anywhere
    cannot vouch for anything.

    Returns:
        ("confirmed", entry)  — hash registered and chain intact
        ("not found", None)   — chain intact but hash not registered
        ("chain broken", None) — chain integrity check failed
    """
    path = resolve_registry_path(registry_path)
    result = verify_chain(path)
    if not result.ok:
        return "chain broken", None

    for line in _read_lines(path):
        entry = json.loads(line)
        if entry.get("report_hash") == report_hash:
            return "confirmed", entry
    return "not found", None
