"""Días hábiles con 2+ recurso_id y 2+ cod_dpto distintos en licencia maternal (histórico)."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from io import StringIO
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.extractor import _build_connection_string  # noqa: E402
from src.settings import load_settings  # noqa: E402

_SQL_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _bracket(raw: str) -> str:
    if not _SQL_IDENT.fullmatch(raw.strip()):
        raise ValueError(f"identificador SQL inválido: {raw!r}")
    return f"[{raw.strip()}]"


def main() -> int:
    p = argparse.ArgumentParser(
        description="Días hábiles con 2+ recurso_id y 2+ dpto RRHH distintos en maternidad."
    )
    p.add_argument(
        "--oldest",
        action="store_true",
        help="Ordenar por más antiguos (por defecto: más recientes).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=15,
        metavar="N",
        help="Máximo de filas (por defecto 15).",
    )
    p.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        default="",
        help="Solo días desde esta fecha (ISO), p. ej. ventana de imputación en Nodum.",
    )
    args = p.parse_args()
    recent_first = not args.oldest
    order = "DESC" if recent_first else "ASC"
    label = "Más recientes" if recent_first else "Más antiguos"

    env = ROOT / ".env"
    load_dotenv(stream=StringIO(env.read_text(encoding="utf-8-sig")), override=True)
    settings = load_settings()
    fi = _bracket(settings.sql_col_lic_fecha_inicio)
    ff = _bracket(settings.sql_col_lic_fecha_fin)
    cc = _bracket(settings.sql_col_trab_centro_costo)
    top_n = max(1, min(args.limit, 500))
    since_sql = ""
    if str(args.since).strip():
        try:
            since_d = date.fromisoformat(str(args.since).strip())
        except ValueError as e:
            print("--since inválido; usar ISO YYYY-MM-DD", file=sys.stderr)
            raise SystemExit(2) from e
        since_sql = f"\n  AND d.d >= CAST('{since_d.isoformat()}' AS date)"

    sql = f"""
WITH leaves AS (
  SELECT t.cod_tit AS recurso_id, tr.{cc} AS dpto, l.{fi} AS fi, l.{ff} AS ff
  FROM cpt_RHLicencias l
  JOIN ct_RHTrabajador tr ON l.cod_trabajador = tr.cod_trabajador
  JOIN ct_titulares t ON tr.cod_tit = t.cod_tit
  WHERE l.cod_tipo_licen = 'maternal'
),
dates AS (
  SELECT CAST('2018-01-01' AS date) AS d
  UNION ALL
  SELECT DATEADD(day, 1, d) FROM dates WHERE d < CAST('2027-01-01' AS date)
)
SELECT TOP ({top_n})
  d.d AS cal_day,
  COUNT(DISTINCT l.recurso_id) AS n_recursos,
  COUNT(DISTINCT l.dpto) AS n_depts
FROM dates d
INNER JOIN leaves l ON d.d BETWEEN CAST(l.fi AS date) AND CAST(l.ff AS date)
WHERE DATEPART(weekday, d.d) BETWEEN 2 AND 6{since_sql}
GROUP BY d.d
HAVING COUNT(DISTINCT l.recurso_id) >= 2 AND COUNT(DISTINCT l.dpto) >= 2
ORDER BY d.d {order}
OPTION (MAXRECURSION 32767);
"""
    conn = pyodbc.connect(_build_connection_string(settings), timeout=30)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        print(f"{label} {top_n} días hábiles con >=2 recurso_id y >=2 dpto distintos:")
        for r in rows:
            print(f"  {r[0]}  recursos={r[1]}  dptos={r[2]}")
        if not rows:
            print("(sin filas)")
            return 1
        pick = rows[0][0]
        d = pick.date() if hasattr(pick, "date") else pick
        print()
        hint = (
            "Sugerencia SYNC_TEST_DATE (coincidencia más reciente):"
            if recent_first
            else "Sugerencia SYNC_TEST_DATE (coincidencia más antigua):"
        )
        print(hint, d.isoformat())
        cur.close()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
