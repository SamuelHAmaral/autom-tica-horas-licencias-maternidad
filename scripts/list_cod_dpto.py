"""Lista los códigos de departamento distintos de ct_RHTrabajador.

Nota: solo lectura. Sirve para completar NODUM_MATERNITY_PROJECT_BY_DEPT.
Correrlo cuando aparece un departamento nuevo, antes de cambiar el .env.
"""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.extractor import _build_connection_string  # noqa: E402
from src.settings import load_settings  # noqa: E402


def main() -> int:
    env = ROOT / ".env"
    load_dotenv(stream=StringIO(env.read_text(encoding="utf-8-sig")), override=True)
    settings = load_settings()
    col = settings.sql_col_trab_centro_costo.strip()
    if not col.replace("_", "").isalnum():
        print("Nombre de columna inválido", file=sys.stderr)
        return 1
    q = f"""
    SELECT DISTINCT LTRIM(RTRIM([{col}])) AS dpto, COUNT(*) AS workers
    FROM ct_RHTrabajador
    WHERE [{col}] IS NOT NULL AND LTRIM(RTRIM([{col}])) <> ''
    GROUP BY LTRIM(RTRIM([{col}]))
    ORDER BY 1;
    """
    conn = pyodbc.connect(_build_connection_string(settings), timeout=30)
    try:
        cur = conn.cursor()
        cur.execute(q)
        print("cod_dpto (SQL_COL_TRAB_CENTRO_COSTO) | trabajadores activos")
        print("-" * 50)
        for row in cur.fetchall():
            print(f"  {row[0]!r}  |  {row[1]}")
        cur.close()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
