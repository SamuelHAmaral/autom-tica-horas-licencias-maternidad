"""Marca de agua del estado local y horas anotadas.

Nota: fija src/backfill_state.py. Usa un archivo temporal, nunca el JSON real.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src import backfill_state


class BackfillStateTests(unittest.TestCase):
    def test_watermark_belongs_to_one_leave_episode(self) -> None:
        data: dict = {"version": 1, "by_recurso": {}}
        inicio = date(2026, 3, 16)
        backfill_state.record_day_ok(data, "100", inicio, date(2026, 3, 18))
        self.assertEqual(
            backfill_state.get_last_ok_fecha(data, "100", inicio),
            date(2026, 3, 18),
        )
        # Un fec_inicio nuevo es otra licencia: no saltear días de la anterior.
        self.assertIsNone(
            backfill_state.get_last_ok_fecha(data, "100", date(2026, 6, 1))
        )

    def test_dates_after_watermark_are_exclusive(self) -> None:
        days = [date(2026, 3, 16), date(2026, 3, 17), date(2026, 3, 18)]
        self.assertEqual(
            backfill_state.dates_after_watermark(days, date(2026, 3, 17)),
            [date(2026, 3, 18)],
        )
        self.assertEqual(backfill_state.dates_after_watermark(days, None), days)

    def test_recorded_hours_accumulate_and_mark_day_full_replaces_them(self) -> None:
        data: dict = {"version": 1, "by_recurso": {}}
        dia = date(2026, 3, 16)
        backfill_state.record_hours(data, "100", dia, 3)
        backfill_state.record_hours(data, "100", dia, 2)
        self.assertEqual(backfill_state.get_recorded_hours(data, "100", dia), 5)
        backfill_state.mark_day_full(data, "100", dia, 8)
        self.assertEqual(backfill_state.get_recorded_hours(data, "100", dia), 8)

    def test_corrupt_file_loads_as_an_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{not json", encoding="utf-8")
            loaded = backfill_state.load(path)
            self.assertEqual(loaded["by_recurso"], {})

    def test_save_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            data = {"version": 1, "by_recurso": {"100": {"fec_inicio": "2026-03-16"}}}
            backfill_state.save(path, data)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["version"], 1)
            self.assertEqual(backfill_state.load(path)["by_recurso"]["100"]["fec_inicio"], "2026-03-16")


if __name__ == "__main__":
    unittest.main()
