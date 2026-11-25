"""Texto SQL armado desde la configuración.

Nota: fija el armado de strings de src/extractor.py. No abre una conexión.
"""

from __future__ import annotations

import unittest
from datetime import date

from src.extractor import build_active_maternity_leaves_sql
from tests.settings_factory import sample_settings


class ActiveLeaveSqlTests(unittest.TestCase):
    def test_column_names_must_be_plain_identifiers(self) -> None:
        settings = sample_settings(sql_col_lic_fecha_inicio="fec_inicio; DROP TABLE x")
        with self.assertRaises(ValueError):
            build_active_maternity_leaves_sql(settings)

    def test_live_run_uses_getdate_and_the_maternal_type(self) -> None:
        sql = build_active_maternity_leaves_sql(sample_settings())
        self.assertIn("cod_tipo_licen = 'maternal'", sql)
        self.assertIn("GETDATE()", sql)
        self.assertIn("[amaral01].dbo.ct_cabidrecursos", sql)
        self.assertIn("LIKE N'%maternidad%'", sql)

    def test_test_date_is_a_parameter_instead_of_getdate(self) -> None:
        sql = build_active_maternity_leaves_sql(
            sample_settings(),
            as_of_calendar=date(2026, 3, 25),
        )
        self.assertIn("CAST(? AS date)", sql)
        self.assertNotIn("GETDATE()", sql)

    def test_active_worker_filter_is_opt_in(self) -> None:
        off = build_active_maternity_leaves_sql(sample_settings())
        on = build_active_maternity_leaves_sql(
            sample_settings(sql_require_trabajador_activo=True)
        )
        self.assertNotIn("estado_trab", off)
        self.assertIn("[estado_trab] = ?", on)


if __name__ == "__main__":
    unittest.main()
