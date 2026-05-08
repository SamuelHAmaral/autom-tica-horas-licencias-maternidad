"""Central logging setup: console + rotating file (maternity_leave_sync.log)."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILENAME = "maternity_leave_sync.log"
MAX_BYTES = 10 * 1024 * 1024  # 10 MiB
BACKUP_COUNT = 5

# ANSI (console only; never written to log file). Respects NO_COLOR and TTY.
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"


def _console_use_color(stream: object) -> bool:
    if os.environ.get("NO_COLOR", "").strip():
        return False
    v = os.environ.get("LOG_COLOR", "1").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    try:
        return bool(getattr(stream, "isatty", lambda: False)())
    except Exception:
        return False


class _ConsoleColorFormatter(logging.Formatter):
    """TTY-only colors for demos; file handler uses plain Formatter."""

    def __init__(self, *args: object, use_color: bool = False, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        if not self._use_color:
            return text
        msg = record.getMessage()
        if record.levelno >= logging.CRITICAL:
            return f"{_BOLD}{_RED}{text}{_RESET}"
        if record.levelno >= logging.ERROR:
            return f"{_RED}{text}{_RESET}"
        if record.levelno >= logging.WARNING:
            return f"{_YELLOW}{text}{_RESET}"
        if record.levelno == logging.DEBUG:
            return f"{_DIM}{text}{_RESET}"
        if (
            record.levelno == logging.INFO
            and "Dry run" in msg
            and "formulario" in msg
        ):
            return f"{_BOLD}{_CYAN}{text}{_RESET}"
        if record.levelno == logging.INFO and " OK " in msg and "estado=0" in msg:
            return f"{_GREEN}{text}{_RESET}"
        if record.levelno == logging.INFO and "dry run recurso_id" in msg:
            return f"{_MAGENTA}{text}{_RESET}"
        return text


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def setup_logging(
    *,
    log_level: int = logging.INFO,
    log_file_name: str = LOG_FILENAME,
) -> None:
    """
    Configure root logger: INFO to console (optional ANSI colors on TTY),
    plain text to rotating file at project root.
    Idempotent if already configured (avoids duplicate handlers on reload).
    """
    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(log_level)
    datefmt = "%Y-%m-%d %H:%M:%S"
    fmt_plain = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    stream = logging.StreamHandler(sys.stdout)
    stream.setLevel(log_level)
    use_color = _console_use_color(sys.stdout)
    stream.setFormatter(
        _ConsoleColorFormatter(
            fmt_plain,
            datefmt=datefmt,
            use_color=use_color,
        )
    )
    root.addHandler(stream)

    log_path = _project_root() / log_file_name
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(fmt_plain, datefmt=datefmt))
    root.addHandler(file_handler)
