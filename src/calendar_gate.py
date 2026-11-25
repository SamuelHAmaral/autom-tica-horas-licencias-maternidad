"""Corte de la corrida programada: solo días de semana, sin los de ct_RHFeriados.

Nota: omitir la corrida es salida 0 desde main. SYNC_FORCE_RUN salta este corte.
"""

from __future__ import annotations

from datetime import date

from src.extractor import fetch_date_is_public_holiday
from src.settings import Settings


def is_weekend(d: date | None = None) -> bool:
    """Sábado o domingo. En Python weekday() es 5 y 6."""
    d = d or date.today()
    return d.weekday() >= 5


def should_run_sync(settings: Settings, today: date | None = None) -> tuple[bool, str | None]:
    """
    (True, None) → seguir con la extracción y la carga.
    (False, motivo) → omitir (salida normal); fines de semana y feriados de RRHH, salvo SYNC_FORCE_RUN.
    """
    if settings.sync_force_run:
        return True, None
    today = today or date.today()
    if is_weekend(today):
        return False, f"weekend ({today:%A})"
    if fetch_date_is_public_holiday(settings, today):
        return False, f"public holiday (ct_RHFeriados) on {today:%Y-%m-%d}"
    return True, None
