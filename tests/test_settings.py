"""Lectura del entorno, en los casos que es fácil equivocarse.

Nota: fija src/settings.py. Cada prueba reemplaza os.environ y después lo restaura.
"""

from __future__ import annotations

import os
import unittest

from src.settings import load_settings


_REQUIRED = {
    "SQL_SERVER_DRIVER": "{ODBC Driver 17 for SQL Server}",
    "SQL_SERVER_SERVER": "sql.example",
    "SQL_SERVER_DATABASE": "RRHHAmaral",
    "SQL_SERVER_UID": "user",
    "SQL_SERVER_PWD": "secret",
    "NODUM_WSDL_URL": "http://nodum.example/wsdl",
    "NODUM_USERNAME": "nodum",
    "NODUM_PASSWORD": "secret",
}


class LoadSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.copy()
        os.environ.clear()
        os.environ.update(_REQUIRED)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._saved)

    def test_missing_required_variable_names_the_key(self) -> None:
        del os.environ["NODUM_PASSWORD"]
        with self.assertRaises(ValueError) as caught:
            load_settings()
        self.assertIn("NODUM_PASSWORD", str(caught.exception))

    def test_parte_scope_must_be_a_known_value(self) -> None:
        os.environ["NODUM_PARTE_SCOPE"] = "month"
        with self.assertRaises(ValueError) as caught:
            load_settings()
        self.assertIn("NODUM_PARTE_SCOPE", str(caught.exception))

    def test_state_file_must_be_a_filename_only(self) -> None:
        os.environ["NODUM_BACKFILL_STATE_FILE"] = "../other.json"
        with self.assertRaises(ValueError):
            load_settings()

    def test_catalog_database_rejects_characters_that_would_break_sql(self) -> None:
        os.environ["AMARAL_CATALOG_DATABASE"] = "amaral01;drop"
        with self.assertRaises(ValueError) as caught:
            load_settings()
        self.assertIn("AMARAL_CATALOG_DATABASE", str(caught.exception))

    def test_department_map_is_stored_casefolded(self) -> None:
        os.environ["NODUM_MATERNITY_PROJECT_BY_DEPT"] = "A001=PRY00375, CDE = PRY00376"
        settings = load_settings()
        self.assertEqual(
            settings.nodum_maternity_project_by_dept,
            {"a001": "PRY00375", "cde": "PRY00376"},
        )

    def test_empty_duplicate_list_disables_the_default_phrases(self) -> None:
        os.environ["NODUM_DUPLICATE_OK_SUBSTRINGS"] = ""
        settings = load_settings()
        self.assertEqual(settings.nodum_duplicate_ok_substrings, ())

    def test_unset_duplicate_list_keeps_the_spanish_defaults(self) -> None:
        settings = load_settings()
        self.assertIn("duplicado", settings.nodum_duplicate_ok_substrings)

    def test_dry_run_defaults_on_when_unset(self) -> None:
        settings = load_settings()
        self.assertTrue(settings.nodum_dry_run)


if __name__ == "__main__":
    unittest.main()
