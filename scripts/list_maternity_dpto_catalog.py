"""Consulta catálogo ERP: recurso / negocio / dpto ligado a proyectos con nom_dpto tipo %maternidad%.

Mismo SQL Server que .env (SQL_SERVER_*). Base catálogo por defecto amaral01; sobrescribir con:

    AMARAL_CATALOG_DATABASE=amaral01

Joins: ct_cabidrecursos -> ct_dptos -> ct_proyectos.
Sirve para alinear ct_RHTrabajador.cod_dpto con nombres de proyecto maternidad / negocio en Nodum.
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
    env = ROOT / ".env"
    load_dotenv(stream=StringIO(env.read_text(encoding="utf-8-sig")), override=True)
    settings = load_settings()

    import os

    db = os.environ.get("AMARAL_CATALOG_DATABASE", "amaral01").strip()
    if not _DB_SAFE.match(db):
        print("AMARAL_CATALOG_DATABASE: solo alfanumérico y guión bajo.", file=sys.stderr)
        return 1

    q = f"""
    SELECT DISTINCT
        cc.cod_id,
        cd.cod_negocio,
        cp.cod_dpto,
        cp.nom_dpto
    FROM [{db}].dbo.ct_cabidrecursos cc
    INNER JOIN [{db}].dbo.ct_dptos cd ON cc.cod_dpto = cd.cod_dpto
    INNER JOIN [{db}].dbo.ct_proyectos cp ON cp.cod_negocio = cd.cod_negocio
    WHERE cp.nom_dpto LIKE '%maternidad%'
    ORDER BY cp.cod_dpto, cd.cod_negocio, cc.cod_id;
    """
    conn = pyodbc.connect(_build_connection_string(settings), timeout=30)
    try:
        cur = conn.cursor()
        try:
            cur.execute(q)
        except pyodbc.Error as e:
            print(
                "Consulta fallida (revisar AMARAL_CATALOG_DATABASE, permisos o nombres de tabla):\n",
                e,
                file=sys.stderr,
            )
            return 2
        cols = [c[0] for c in cur.description] if cur.description else []
        print(f"Base: {db} | columnas: {cols}")
        print("-" * 100)
        n = 0
        for row in cur.fetchall():
            print("  " + " | ".join(repr(x).strip() for x in row))
            n += 1
        print("-" * 100)
        print(f"Filas: {n}")
        cur.close()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
