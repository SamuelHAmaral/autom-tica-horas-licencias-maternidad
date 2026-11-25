"""Corte de fin de semana.

Nota: fija src/calendar_gate.py. Estos casos vuelven antes de la consulta SQL de feriados.
"""

from __future__ import annotations

import unittest
from datetime import date

from src.calendar_gate import is_weekend, should_run_sync
from tests.settings_factory import sample_settings


class CalendarGateTests(unittest.TestCase):
    def test_saturday_is_a_weekend(self) -> None:
        self.assertTrue(is_weekend(date(2026, 3, 21)))
        self.assertFalse(is_weekend(date(2026, 3, 20)))

    def test_weekend_skips_without_calling_sql(self) -> None:
        ok, reason = should_run_sync(
            sample_settings(),
            today=date(2026, 3, 21),
        )
        self.assertFalse(ok)
        self.assertIn("weekend", reason or "")

    def test_force_run_allows_the_weekend(self) -> None:
        ok, reason = should_run_sync(
            sample_settings(sync_force_run=True),
            today=date(2026, 3, 21),
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
