"""Selección de días hábiles y forma del proyecto / parte de Nodum.

Nota: fija src/transformer.py. Sin base de datos. Las fechas de abajo son días reales de 2026.
"""

from __future__ import annotations

import unittest
from datetime import date

from src.transformer import (
    build_daily_payloads,
    holiday_range_for_sync,
    leave_working_dates_backfill_to_run_date,
    leave_working_dates_in_current_week,
    resolve_g2_centrode_costo,
)
from tests.settings_factory import sample_settings


def _leave(inicio: str, fin: str, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "recurso_id": "100",
        "centro_costo": "A001",
        "fecha_inicio": date.fromisoformat(inicio),
        "fecha_fin": date.fromisoformat(fin),
    }
    row.update(extra)
    return row


class WorkingDayTests(unittest.TestCase):
    def test_catch_up_keeps_weekdays_through_the_run_date(self) -> None:
        # 2026-03-16 es lunes. Fecha de corrida: viernes 2026-03-20. El miércoles es feriado.
        days = leave_working_dates_backfill_to_run_date(
            _leave("2026-03-16", "2026-03-31"),
            holiday_dates={date(2026, 3, 18)},
            run_date=date(2026, 3, 20),
        )
        self.assertEqual(
            days,
            [
                date(2026, 3, 16),
                date(2026, 3, 17),
                date(2026, 3, 19),
                date(2026, 3, 20),
            ],
        )

    def test_catch_up_stops_at_leave_end_and_skips_the_weekend(self) -> None:
        # Del viernes 20 al lunes 23: sábado y domingo no son partes.
        days = leave_working_dates_backfill_to_run_date(
            _leave("2026-03-20", "2026-04-30"),
            holiday_dates=set(),
            run_date=date(2026, 3, 23),
        )
        self.assertEqual(days, [date(2026, 3, 20), date(2026, 3, 23)])

    def test_catch_up_is_empty_when_leave_starts_after_the_run_date(self) -> None:
        days = leave_working_dates_backfill_to_run_date(
            _leave("2026-03-25", "2026-04-30"),
            holiday_dates=set(),
            run_date=date(2026, 3, 20),
        )
        self.assertEqual(days, [])

    def test_week_scope_stays_inside_the_iso_week(self) -> None:
        # Miércoles 2026-03-25 → semana ISO del lunes 23 al domingo 29.
        days = leave_working_dates_in_current_week(
            _leave("2026-03-16", "2026-03-31"),
            holiday_dates=set(),
            today=date(2026, 3, 25),
        )
        self.assertEqual(
            days,
            [
                date(2026, 3, 23),
                date(2026, 3, 24),
                date(2026, 3, 25),
                date(2026, 3, 26),
                date(2026, 3, 27),
            ],
        )

    def test_holiday_query_span_follows_the_scope(self) -> None:
        rows = [_leave("2026-03-02", "2026-04-30"), _leave("2026-03-16", "2026-04-30")]
        self.assertEqual(
            holiday_range_for_sync("today", rows, date(2026, 3, 20)),
            (date(2026, 3, 2), date(2026, 3, 20)),
        )
        self.assertEqual(
            holiday_range_for_sync("week", rows, date(2026, 3, 25)),
            (date(2026, 3, 23), date(2026, 3, 29)),
        )


class ProyectoResolutionTests(unittest.TestCase):
    def test_erp_proyecto_wins_over_the_department_map(self) -> None:
        settings = sample_settings()
        row = _leave("2026-03-16", "2026-03-31", erp_maternidad_pry="PRY00999")
        self.assertEqual(resolve_g2_centrode_costo(row, settings), "PRY00999")

    def test_department_map_is_case_insensitive(self) -> None:
        settings = sample_settings(maternity_pry_use_cabidrecurso=False)
        row = _leave("2026-03-16", "2026-03-31", centro_costo="a001")
        self.assertEqual(resolve_g2_centrode_costo(row, settings), "PRY00375")

    def test_unmapped_department_uses_the_default_proyecto(self) -> None:
        settings = sample_settings(maternity_pry_use_cabidrecurso=False)
        row = _leave("2026-03-16", "2026-03-31", centro_costo="ZZZ")
        self.assertEqual(resolve_g2_centrode_costo(row, settings), "PRY00380")


class PayloadTests(unittest.TestCase):
    def test_one_parte_per_day_with_partial_hours(self) -> None:
        settings = sample_settings(maternity_pry_use_cabidrecurso=False)
        monday = date(2026, 3, 16)
        payloads = build_daily_payloads(
            _leave("2026-03-16", "2026-03-31"),
            settings,
            [monday],
            hours_by_date={monday: 5},
        )
        self.assertEqual(len(payloads), 1)
        g1 = payloads[0]["General"]["G1"]
        g2 = payloads[0]["General"]["G2"][0]
        self.assertEqual(g1["FechaDocumento"], "2026-03-16")
        self.assertEqual(g1["CodigoIdentificacion"], "100")
        self.assertEqual(g1["CodigoEmpresa"], "01")
        self.assertEqual(g2["CentrodeCosto"], "PRY00375")
        self.assertEqual(g2["Horasdeduracion"], 5)
        self.assertNotIn("observaciones_1", g2)

    def test_optional_g2_note_is_included_only_when_set(self) -> None:
        settings = sample_settings(
            maternity_pry_use_cabidrecurso=False,
            nodum_g2_observaciones_1="nota",
        )
        payloads = build_daily_payloads(
            _leave("2026-03-16", "2026-03-31"),
            settings,
            [date(2026, 3, 16)],
        )
        self.assertEqual(payloads[0]["General"]["G2"][0]["observaciones_1"], "nota")


if __name__ == "__main__":
    unittest.main()
