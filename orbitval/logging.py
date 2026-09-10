"""
orbitval/logging.py

Centralized logging for OrbitVal.
Provides structured logging to terminal, log file, and ORF report.

Usage in any module:
    from orbitval.logging import get_logger
    log = get_logger("tle")
    log.info("Cache hit for '%s'", satellite_name)
    log.warning("Stale cache fallback")
    log.debug("TLE epoch: %s", epoch)

The CLI controls verbosity:
    orbitval run ...           # INFO — normal
    orbitval run ... --verbose # DEBUG — full internal state
    orbitval run ... --quiet   # WARNING+ only
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _utc_now() -> datetime:
    """Naive UTC 'now'. Replaces datetime.utcnow(), which is deprecated,
    while keeping the exact same naive-UTC value and string format."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Run event buffer (for ORF report embedding) ───────────────

_run_events: list[dict] = []
_log_file_handler: Optional[logging.FileHandler] = None


def _record_event(level: str, module: str, msg: str) -> None:
    """Record a log event for embedding in the ORF report."""
    _run_events.append({
        "timestamp": _utc_now().isoformat() + "Z",
        "level": level,
        "module": module,
        "msg": msg,
    })


def get_run_events() -> list[dict]:
    """
    Return all log events recorded during this run.
    Embedded in the ORF JSON report under 'run_log'.
    """
    return list(_run_events)


def clear_run_events() -> None:
    """Clear the run event buffer."""
    _run_events.clear()


def set_run_events(events: list[dict]) -> None:
    """Replace the run event buffer with `events`.

    Used by the harness to seed a run's audit trail with the events
    recorded while the orbit was being set up (TLE fetch, propagation,
    eclipse scan). Those happen before run() is called but are part of
    the run's provenance, so they belong in the report's run_log.
    """
    _run_events.clear()
    _run_events.extend(events)


# ── Custom formatter ──────────────────────────────────────────

class OrbitValFormatter(logging.Formatter):
    """
    Formats log records as:
    2026-03-17 05:17:42 UTC | INFO    | tle     | message
    """

    LEVEL_COLORS = {
        "DEBUG":    "\033[36m",    # cyan
        "INFO":     "\033[32m",    # green
        "WARNING":  "\033[33m",    # yellow
        "ERROR":    "\033[31m",    # red
        "CRITICAL": "\033[35m",    # magenta
    }
    RESET = "\033[0m"

    def __init__(self, colorize: bool = True):
        super().__init__()
        self.colorize = colorize

    @staticmethod
    def format_parts(timestamp: str, levelname: str, name: str, msg: str) -> str:
        """Format an already-recorded event (used to replay buffered events)."""
        return f"{timestamp} | {levelname.ljust(8)} | {name.ljust(12)} | {msg}"

    def format(self, record: logging.LogRecord) -> str:
        timestamp = _utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
        level = record.levelname.ljust(8)
        module = record.name.ljust(12)
        msg = record.getMessage()

        if self.colorize and sys.stdout.isatty():
            color = self.LEVEL_COLORS.get(record.levelname, "")
            level_str = f"{color}{level}{self.RESET}"
        else:
            level_str = level

        return f"{timestamp} | {level_str} | {module} | {msg}"


# ── OrbitVal logger with event capture ────────────────────────

class OrbitValLogger(logging.Logger):
    """
    Extended logger that also records events for ORF report embedding.
    """

    def info(self, msg, *args, **kwargs):
        super().info(msg, *args, **kwargs)
        _record_event("INFO", self.name, msg % args if args else str(msg))

    def warning(self, msg, *args, **kwargs):
        super().warning(msg, *args, **kwargs)
        _record_event("WARNING", self.name, msg % args if args else str(msg))

    def error(self, msg, *args, **kwargs):
        super().error(msg, *args, **kwargs)
        _record_event("ERROR", self.name, msg % args if args else str(msg))

    def debug(self, msg, *args, **kwargs):
        super().debug(msg, *args, **kwargs)
        # Only record debug events if debug level is active
        if self.isEnabledFor(logging.DEBUG):
            _record_event("DEBUG", self.name, msg % args if args else str(msg))


# ── Logger registry ───────────────────────────────────────────

logging.setLoggerClass(OrbitValLogger)
_loggers: dict[str, OrbitValLogger] = {}
_root_level = logging.INFO


def get_logger(module_name: str) -> OrbitValLogger:
    """
    Get or create a named logger for a module.

    Args:
        module_name: short name e.g. "tle", "runner", "injection"

    Returns:
        OrbitValLogger instance
    """
    if module_name not in _loggers:
        logger = logging.getLogger(f"orbitval.{module_name}")
        logger.setLevel(_root_level)

        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(OrbitValFormatter(colorize=True))
            logger.addHandler(handler)
            logger.propagate = False

        _loggers[module_name] = logger

    return _loggers[module_name]


def set_log_level(level: str) -> None:
    """
    Set the log level for all OrbitVal loggers.

    Args:
        level: "DEBUG", "INFO", "WARNING", "ERROR"
    """
    global _root_level
    numeric = getattr(logging, level.upper(), logging.INFO)
    _root_level = numeric
    for logger in _loggers.values():
        logger.setLevel(numeric)


def init_run_log(output_path: Path, replay_buffered: bool = True) -> None:
    """
    Initialize a file handler for this run.
    Writes all log events to a .log file alongside the report.

    Args:
        output_path: path to the JSON or PDF report —
                     .log file will use the same stem
        replay_buffered: write the events already in the run buffer (the
                     orbit setup trail recorded before this run started)
                     into the new .log file, so the file and the report's
                     run_log describe the same run.
    """
    global _log_file_handler

    log_path = Path(output_path).with_suffix(".log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Detach the previous run's file handler so this run's events
    # don't leak into an earlier run's audit log.
    if _log_file_handler is not None:
        for logger in _loggers.values():
            logger.removeHandler(_log_file_handler)
        _log_file_handler.close()

    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setFormatter(OrbitValFormatter(colorize=False))
    handler.setLevel(logging.DEBUG)

    _log_file_handler = handler

    for logger in _loggers.values():
        logger.addHandler(handler)

    # Replay the orbit-setup events recorded before this run started, so
    # the .log file carries the same provenance as the report's run_log.
    # These happened before the header, so they are written first.
    if replay_buffered:
        for event in _run_events:
            handler.stream.write(
                OrbitValFormatter.format_parts(
                    event["timestamp"].replace("T", " ").replace("Z", " UTC"),
                    event["level"], event["module"], event["msg"],
                ) + "\n"
            )
        handler.flush()

    # Write header
    header_logger = get_logger("orbitval")
    header_logger.info("OrbitVal run started — log: %s", log_path)