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
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── Run event buffer (for ORF report embedding) ───────────────

_run_events: list[dict] = []
_log_file_handler: Optional[logging.FileHandler] = None


def _record_event(level: str, module: str, msg: str) -> None:
    """Record a log event for embedding in the ORF report."""
    _run_events.append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
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
    """Clear the run event buffer. Called at start of each run."""
    _run_events.clear()


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

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
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


def init_run_log(output_path: Path) -> None:
    """
    Initialize a file handler for this run.
    Writes all log events to a .log file alongside the report.

    Args:
        output_path: path to the JSON or PDF report —
                     .log file will use the same stem
    """
    global _log_file_handler

    log_path = Path(output_path).with_suffix(".log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setFormatter(OrbitValFormatter(colorize=False))
    handler.setLevel(logging.DEBUG)

    _log_file_handler = handler

    for logger in _loggers.values():
        logger.addHandler(handler)

    # Write header
    header_logger = get_logger("orbitval")
    header_logger.info("OrbitVal run started — log: %s", log_path)