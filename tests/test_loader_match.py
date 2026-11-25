"""Lectura de Nodum: qué líneas cuentan como horas de maternidad.

Nota: fija src/loader.py. Las horas de otro proyecto no tienen que contar como completas.
"""

from __future__ import annotations

import unittest

from src.loader import _read_line_matches_maternity_proyecto
from tests.settings_factory import sample_settings


class ReadLineMatchTests(unittest.TestCase):
    def test_hours_on_another_proyecto_do_not_count(self) -> None:
        settings = sample_settings()
        line = {
            "R_NombreCentrodeCostos": "PRY00001 otro",
            "R_NombredeActividad": "desarrollo",
        }
        self.assertFalse(
            _read_line_matches_maternity_proyecto(
                settings, line, g2_centrode_costo="PRY00380"
            )
        )

    def test_resolved_proyecto_code_counts(self) -> None:
        settings = sample_settings()
        line = {
            "R_NombreCentrodeCostos": "proyecto PRY00380",
            "R_NombredeActividad": "horas",
        }
        self.assertTrue(
            _read_line_matches_maternity_proyecto(
                settings, line, g2_centrode_costo="PRY00380"
            )
        )

    def test_fallback_substring_counts_when_the_code_is_absent(self) -> None:
        settings = sample_settings()
        line = {
            "R_NombreCentrodeCostos": "Licencia Maternidad",
            "R_NombredeActividad": "001",
        }
        self.assertTrue(
            _read_line_matches_maternity_proyecto(
                settings, line, g2_centrode_costo="PRY00380"
            )
        )

    def test_match_off_counts_every_line(self) -> None:
        settings = sample_settings(nodum_read_match_resolved_proyecto=False)
        line = {"R_NombreCentrodeCostos": "PRY00001", "R_NombredeActividad": "x"}
        self.assertTrue(
            _read_line_matches_maternity_proyecto(
                settings, line, g2_centrode_costo="PRY00380"
            )
        )


if __name__ == "__main__":
    unittest.main()
