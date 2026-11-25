"""Lista códigos de negocio del ERP y su proyecto de maternidad (PRY).

Nota: solo lectura. Un proyecto entra si ct_proyectos.nom_dpto contiene "maternidad".
Lista corta para revisar NODUM_MATERNITY_PROJECT_BY_DEPT. No carga partes.
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
    if not _DB_SAFE.match(erp):
        print("AMARAL_CATALOG_DATABASE inválido", file=sys.stderr)
        return 1

    q = f"""
    SELECT DISTINCT
        LTRIM(RTRIM(cd.cod_negocio)) AS cod_negocio,
        LTRIM(RTRIM(cp.cod_dpto)) AS proyecto_maternidad,
        LTRIM(RTRIM(cp.nom_dpto)) AS nom_maternidad
    FROM [{erp}].dbo.ct_cabidrecursos cc
    INNER JOIN [{erp}].dbo.ct_dptos cd ON cc.cod_dpto = cd.cod_dpto
    INNER JOIN [{erp}].dbo.ct_proyectos cp ON cp.cod_negocio = cd.cod_negocio
    WHERE cp.nom_dpto LIKE '%maternidad%'
    ORDER BY cod_negocio, proyecto_maternidad;
    """
    conn = pyodbc.connect(_build_connection_string(settings), timeout=30)
    try:
        cur = conn.cursor()
        cur.execute(q)
        print("cod_negocio | proyecto (PRY) | nom_maternidad")
        print("-" * 90)
        for row in cur.fetchall():
            print(f"  {row[0]!r:14} | {row[1]!r:16} | {row[2]}")
        cur.close()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
