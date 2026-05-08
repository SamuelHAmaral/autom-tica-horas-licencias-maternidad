"""Gate scheduled sync: weekdays only, excluding ct_RHFeriados."""

from __future__ import annotations

from datetime import date

from src.extractor import fetch_date_is_public_holiday
from src.settings import Settings


def is_weekend(d: date | None = None) -> bool:
    d = d or date.today()
    return d.weekday() >= 5


def should_run_sync(settings: Settings, today: date | None = None) -> tuple[bool, str | None]:
    """
    (True, None) → proceed with extract/load.
    (False, reason) → skip (normal exit); weekends and HR holidays unless SYNC_FORCE_RUN.
    """
    if settings.sync_force_run:
        return True, None
    today = today or date.today()
    if is_weekend(today):
        return False, f"weekend ({today:%A})"
    if fetch_date_is_public_holiday(settings, today):
        return False, f"public holiday (ct_RHFeriados) on {today:%Y-%m-%d}"
    return True, None
