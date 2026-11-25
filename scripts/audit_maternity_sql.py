"""Muestra a quién vería la sincronización en licencia maternal activa, y el proyecto de Nodum resuelto.

Nota: solo lectura. Usa el mismo SQL que el job, incluido SYNC_TEST_DATE si está definido.
No llama a procesarAlta y no actualiza el archivo de estado.
"""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.extractor import _build_connection_string, fetch_active_leaves  # noqa: E402
from src.settings import load_settings  # noqa: E402
from src.transformer import resolve_g2_centrode_costo  # noqa: E402


def main() -> int:
    env = ROOT / ".env"
    load_dotenv(stream=StringIO(env.read_text(encoding="utf-8-sig")), override=True)
    settings = load_settings()
    rows = fetch_active_leaves(settings)

    print(
        "=== Consulta del sync: maternal + ventana activa (GETDATE() salvo SYNC_TEST_DATE en .env) ==="
    )
    print(f"Filas: {len(rows)}")
    seen: dict[str, list] = {}
    for r in rows:
        rid = str(r["recurso_id"]).strip()
        seen.setdefault(rid, []).append(r)
    for rid, lst in sorted(seen.items()):
        r0 = lst[0]
        nodum_cc = resolve_g2_centrode_costo(r0, settings)
        erp_raw = r0.get("erp_maternidad_pry")
        erp_bit = f"  erp_maternidad_pry={erp_raw!r}" if erp_raw is not None else ""
        disp = r0.get("recurso_display_name")
        name_bit = f"  nombre={disp!r}" if disp is not None and str(disp).strip() else ""
        print(
            f"  recurso_id={rid!r}  ({len(lst)} fila(s) licencia)  "
            f"{r0['fecha_inicio']} .. {r0['fecha_fin']}  "
            f"SQL dept={r0.get('centro_costo')!r}{name_bit}{erp_bit}  "
            f"-> Nodum G2.CentrodeCosto={nodum_cc!r}"
        )

    # Nombres a ojo desde ct_titulares, si hace falta completar el listado.
    ids = list(seen.keys())
    if not ids:
        return 0
    conn_str = _build_connection_string(settings)
    conn = pyodbc.connect(conn_str, timeout=30)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'ct_titulares'
              AND DATA_TYPE IN ('varchar', 'nvarchar', 'char', 'nchar')
            ORDER BY ORDINAL_POSITION
            """
        )
        name_cols = [row[0] for row in cur.fetchall()]
        candidates = [
            c
            for c in name_cols
            if any(x in c.lower() for x in ("nom", "ape", "name", "raz", "denom"))
            and c.lower() != "cod_tit"
        ]
        if not candidates:
            candidates = [c for c in name_cols if c.lower() != "cod_tit"][:6]
        cols = ["cod_tit"] + candidates[:5]
        placeholders = ",".join("?" * len(ids))
        col_sql = ", ".join(f"[{c}]" for c in cols)
        q = f"SELECT DISTINCT {col_sql} FROM ct_titulares WHERE cod_tit IN ({placeholders})"
        cur.execute(q, ids)
        colnames = [d[0] for d in cur.description]
        print()
        print("=== ct_titulares (columnas de nombre) ===")
        for rec in cur.fetchall():
            print(" ", dict(zip(colnames, rec)))
        cur.close()
    finally:
        conn.close()

    print()
    print("Recursos distintos (el job procesa una vez por id):", len(seen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
