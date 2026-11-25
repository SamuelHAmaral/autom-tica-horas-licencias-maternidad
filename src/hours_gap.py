"""Horas que todavía faltan en cada día hábil (estado local contra la lectura de Nodum).

Nota: las horas ya cargadas son el máximo de las dos fuentes. Cualquiera de las
dos puede marcar el día como completo, y ninguna puede borrar lo que contó la otra.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

# Ignora el polvo de punto flotante para no enviar otro parte por 8.0000000001.
_HOURS_EPSILON = 1e-9


@dataclass(frozen=True)
class DayHours:
    """Un día candidato después de comparar el estado local con la lectura de Nodum."""

    dia: date
    missing: float
    already: float
    already_local: float
    already_nodum: float

    @property
    def complete(self) -> bool:
        return self.missing <= _HOURS_EPSILON


def classify_working_day_hours(
    valid_dates: Sequence[date],
    *,
    target_daily_hours: float,
    local_hours_by_date: Mapping[date, float],
    nodum_hours_by_date: Mapping[date, float],
) -> list[DayHours]:
    """
    Horas que todavía hay que enviar en cada día hábil.

    Lo ya cargado es ``max(estado local, lectura de Nodum)``. Cualquiera de las
    dos fuentes puede marcar el día como completo, y ninguna borra las horas que
    la otra ya contó. Los días que llegan a ``target_daily_hours`` quedan ``complete``.
    """
    target = float(target_daily_hours)
    classified: list[DayHours] = []
    for dia in valid_dates:
        already_local = float(local_hours_by_date.get(dia, 0.0))
        already_nodum = float(nodum_hours_by_date.get(dia, 0.0))
        already = max(already_local, already_nodum)
        missing = max(0.0, target - already)
        classified.append(
            DayHours(
                dia=dia,
                missing=missing,
                already=already,
                already_local=already_local,
                already_nodum=already_nodum,
            )
        )
    return classified
