"""Traba previa que se usa con SYNC_PRODUCTION=1.

Nota: fija src/production_checks.py. El modo estricto bloquea la prueba en seco y una fecha de prueba.
"""

from __future__ import annotations

import unittest
from datetime import date

from src.production_checks import run_production_checks
from tests.settings_factory import sample_settings


class ProductionCheckTests(unittest.TestCase):
    def test_strict_mode_blocks_dry_run_and_a_test_date(self) -> None:
        settings = sample_settings(
            nodum_dry_run=True,
            sync_test_date=date(2026, 3, 25),
        )
        result = run_production_checks(settings, strict=True)
        self.assertFalse(result.ok)
        self.assertTrue(any("NODUM_DRY_RUN" in msg for msg in result.errors))
        self.assertTrue(any("SYNC_TEST_DATE" in msg for msg in result.errors))

    def test_without_strict_mode_the_same_settings_only_warn(self) -> None:
        settings = sample_settings(nodum_dry_run=True, sync_test_date=date(2026, 3, 25))
        result = run_production_checks(settings, strict=False)
        self.assertTrue(result.ok)
        self.assertGreaterEqual(len(result.warnings), 2)

    def test_read_back_off_warns_but_does_not_block(self) -> None:
        settings = sample_settings(nodum_read_operation="")
        result = run_production_checks(settings, strict=True)
        self.assertTrue(result.ok)
        self.assertTrue(any("NODUM_READ_OPERATION" in msg for msg in result.warnings))

    def test_counting_every_proyecto_warns(self) -> None:
        settings = sample_settings(nodum_read_match_resolved_proyecto=False)
        result = run_production_checks(settings, strict=True)
        self.assertTrue(result.ok)
        self.assertTrue(
            any("NODUM_READ_MATCH_RESOLVED_PROYECTO" in msg for msg in result.warnings)
        )


if __name__ == "__main__":
    unittest.main()
