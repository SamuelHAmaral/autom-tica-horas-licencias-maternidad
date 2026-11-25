"""Une los códigos de departamento de RRHH con el cod_negocio del ERP.

Nota: solo lectura. Las claves coinciden solo si ct_RHTrabajador.cod_dpto es igual a ct_dptos.cod_dpto.
La base del ERP es AMARAL_CATALOG_DATABASE (por defecto amaral01).
"""

from __future__ import annotations

import re
import sys
from io import StringIO
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.extractor import _build_connection_string  # noqa: E402
from src.settings import load_settings  # noqa: E402

_DB_SAFE = re.compile(r"^[A-Za-z0-9_]+$")


def main() -> int:
    import os

    env = ROOT / ".env"
    load_dotenv(stream=StringIO(env.read_text(encoding="utf-8-sig")), override=True)
    settings = load_settings()
    erp = os.environ.get("AMARAL_CATALOG_DATABASE", "amaral01").strip()
    hr_db = settings.sql_database.strip()
    col = settings.sql_col_trab_centro_costo.strip()
    if not _DB_SAFE.match(erp) or not _DB_SAFE.match(hr_db):
        print("Nombre de base inválido en .env", file=sys.stderr)
        return 1
    if not col.replace("_", "").isalnum():
        return 1

    q = f"""
    SELECT DISTINCT
        LTRIM(RTRIM(tr.[{col}])) AS hr_cod_dpto,
        LTRIM(RTRIM(cd.cod_negocio)) AS cod_negocio
    FROM [{hr_db}].dbo.ct_RHTrabajador tr
    INNER JOIN [{erp}].dbo.ct_dptos cd
        ON LTRIM(RTRIM(tr.[{col}])) = LTRIM(RTRIM(cd.cod_dpto))
    WHERE tr.[{col}] IS NOT NULL AND LTRIM(RTRIM(tr.[{col}])) <> ''
    ORDER BY hr_cod_dpto;
    """
    conn = pyodbc.connect(_build_connection_string(settings), timeout=30)
    try:
        cur = conn.cursor()
        try:
            cur.execute(q)
        except pyodbc.Error as e:
            print(
                "Fallo del JOIN (cod_dpto RRHH puede no coincidir con ERP ct_dptos.cod_dpto):\n",
                e,
                file=sys.stderr,
            )
            return 2
        print(f"RRHH [{hr_db}] ct_RHTrabajador.[{col}]  ->  ERP [{erp}] ct_dptos.cod_negocio")
        print("-" * 60)
        for row in cur.fetchall():
            print(f"  {row[0]!r:20} -> {row[1]!r}")
        cur.close()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
