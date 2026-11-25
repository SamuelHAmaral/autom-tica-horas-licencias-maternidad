"""Qué horas faltan todavía en un día hábil.

Nota: fija la regla max(local, Nodum) de src/hours_gap.py.
"""

from __future__ import annotations

import unittest
from datetime import date

from src.hours_gap import classify_working_day_hours


class ClassifyWorkingDayHoursTests(unittest.TestCase):
    def test_sends_only_the_gap_up_to_the_daily_target(self) -> None:
        monday = date(2026, 3, 16)
        classified = classify_working_day_hours(
            [monday],
            target_daily_hours=8,
            local_hours_by_date={monday: 3},
            nodum_hours_by_date={monday: 0},
        )
        self.assertEqual(len(classified), 1)
        self.assertFalse(classified[0].complete)
        self.assertEqual(classified[0].missing, 5)

    def test_either_source_can_mark_the_day_complete(self) -> None:
        monday = date(2026, 3, 16)
        classified = classify_working_day_hours(
            [monday],
            target_daily_hours=8,
            local_hours_by_date={monday: 0},
            nodum_hours_by_date={monday: 8},
        )
        self.assertTrue(classified[0].complete)
        self.assertEqual(classified[0].already, 8)
        self.assertEqual(classified[0].missing, 0)

    def test_local_hours_are_not_erased_when_nodum_read_is_lower(self) -> None:
        monday = date(2026, 3, 16)
        classified = classify_working_day_hours(
            [monday],
            target_daily_hours=8,
            local_hours_by_date={monday: 8},
            nodum_hours_by_date={monday: 2},
        )
        self.assertTrue(classified[0].complete)
        self.assertEqual(classified[0].already_local, 8)
        self.assertEqual(classified[0].already_nodum, 2)

    def test_missing_sources_count_as_zero(self) -> None:
        monday = date(2026, 3, 16)
        classified = classify_working_day_hours(
            [monday],
            target_daily_hours=8,
            local_hours_by_date={},
            nodum_hours_by_date={},
        )
        self.assertEqual(classified[0].missing, 8)
        self.assertFalse(classified[0].complete)


if __name__ == "__main__":
    unittest.main()
