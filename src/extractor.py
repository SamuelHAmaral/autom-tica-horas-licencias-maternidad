"""Extract active maternity leaves from SQL Server."""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

import pyodbc

from src.settings import Settings

logger = logging.getLogger(__name__)

# Login timeout (seconds) for the initial connection attempt
SQL_LOGIN_TIMEOUT = 30
# Query timeout (seconds) for statement execution
SQL_QUERY_TIMEOUT = 60

_SQL_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _bracket_ident(raw: str, label: str) -> str:
    """Allow only simple identifiers; emit bracket-quoted name for SQL Server."""
    name = raw.strip()
    if not _SQL_IDENT.fullmatch(name):
        raise ValueError(
            f"{label} must be a single SQL identifier (letters, digits, underscore): {raw!r}"
        )
    return f"[{name}]"


def _titular_display_name_sql_fragment(settings: Settings) -> str:
    """Extra SELECT column recurso_display_name from ct_titulares alias t, or empty string."""
    nom = settings.sql_col_tit_nombre.strip()
    ape = settings.sql_col_tit_apellido.strip()
    if not nom and not ape:
        return ""
    if nom and ape:
        cn = _bracket_ident(nom, "SQL_COL_TIT_NOMBRE")
        ca = _bracket_ident(ape, "SQL_COL_TIT_APELLIDO")
        return f""",
    LTRIM(RTRIM(
      ISNULL(LTRIM(RTRIM(CAST(t.{cn} AS NVARCHAR(260)))), N'')
      + N' '
      + ISNULL(LTRIM(RTRIM(CAST(t.{ca} AS NVARCHAR(260)))), N'')
    )) AS recurso_display_name"""
    if nom:
        cn = _bracket_ident(nom, "SQL_COL_TIT_NOMBRE")
        return f",\n    LTRIM(RTRIM(CAST(t.{cn} AS NVARCHAR(500)))) AS recurso_display_name"
    ca = _bracket_ident(ape, "SQL_COL_TIT_APELLIDO")
    return f",\n    LTRIM(RTRIM(CAST(t.{ca} AS NVARCHAR(500)))) AS recurso_display_name"


def build_active_maternity_leaves_sql(
    settings: Settings, as_of_calendar: date | None = None
) -> str:
    """
    Build SELECT using physical column names from settings (overridable via .env).
    Result columns: recurso_id, centro_costo, fecha_inicio, fecha_fin;
    optional erp_maternidad_pry when maternity_pry_use_cabidrecurso;
    optional recurso_display_name when SQL_COL_TIT_NOMBRE / SQL_COL_TIT_APELLIDO are set.

    Optional filter: only employed workers (parameterized estado value).

    When as_of_calendar is set (e.g. SYNC_TEST_DATE), rows are those with that
    calendar day inside [fecha_inicio, fecha_fin] instead of GETDATE().
    """
    col_fi = _bracket_ident(settings.sql_col_lic_fecha_inicio, "SQL_COL_LIC_FECHA_INICIO")
    col_ff = _bracket_ident(settings.sql_col_lic_fecha_fin, "SQL_COL_LIC_FECHA_FIN")
    col_cc = _bracket_ident(settings.sql_col_trab_centro_costo, "SQL_COL_TRAB_CENTRO_COSTO")
    if as_of_calendar is not None:
        window_clause = f"\n  AND CAST(? AS date) BETWEEN l.{col_fi} AND l.{col_ff}"
    else:
        window_clause = f"\n  AND GETDATE() BETWEEN l.{col_fi} AND l.{col_ff}"
    active_clause = ""
    if settings.sql_require_trabajador_activo:
        col_est = _bracket_ident(settings.sql_col_trab_estado, "SQL_COL_TRAB_ESTADO")
        active_clause = f"\n  AND tr.{col_est} = ?"
    erp_pry_sql = ""
    if settings.maternity_pry_use_cabidrecurso:
        db = settings.amaral_catalog_database
        erp_pry_sql = f""",
    (
      SELECT TOP 1 LTRIM(RTRIM(cp.cod_dpto))
      FROM [{db}].dbo.ct_cabidrecursos cc
      INNER JOIN [{db}].dbo.ct_dptos cd ON cc.cod_dpto = cd.cod_dpto
      INNER JOIN [{db}].dbo.ct_proyectos cp ON cp.cod_negocio = cd.cod_negocio
      WHERE LTRIM(RTRIM(CAST(cc.cod_id AS NVARCHAR(200)))) = LTRIM(RTRIM(CAST(t.cod_tit AS NVARCHAR(200))))
        AND cp.nom_dpto LIKE N'%maternidad%'
      ORDER BY LTRIM(RTRIM(cp.cod_dpto))
    ) AS erp_maternidad_pry"""
    titular_name_sql = _titular_display_name_sql_fragment(settings)
    return f"""
SELECT
    t.cod_tit AS recurso_id,
    tr.{col_cc} AS centro_costo,
    l.{col_fi} AS fecha_inicio,
    l.{col_ff} AS fecha_fin{erp_pry_sql}{titular_name_sql}
FROM cpt_RHLicencias l
JOIN ct_RHTrabajador tr ON l.cod_trabajador = tr.cod_trabajador
JOIN ct_titulares t ON tr.cod_tit = t.cod_tit
WHERE l.cod_tipo_licen = 'maternal'{window_clause}{active_clause};
"""


def build_holiday_exists_sql(settings: Settings) -> str:
    """Single-row probe: ct_RHFeriados date column vs calendar day (parameter)."""
    col_f = _bracket_ident(settings.sql_col_feriado_fecha, "SQL_COL_FERIADO_FECHA")
    return f"""
SELECT TOP 1 1 AS holiday_hit
FROM ct_RHFeriados
WHERE CAST({col_f} AS date) = ?;
"""


def build_holiday_dates_in_range_sql(settings: Settings) -> str:
    """All distinct calendar dates in ct_RHFeriados between range_start and range_end (inclusive)."""
    col_f = _bracket_ident(settings.sql_col_feriado_fecha, "SQL_COL_FERIADO_FECHA")
    return f"""
SELECT DISTINCT CAST({col_f} AS date) AS d
FROM ct_RHFeriados
WHERE CAST({col_f} AS date) BETWEEN ? AND ?;
"""


def _build_connection_string(settings: Settings) -> str:
    driver = settings.sql_driver.strip("{}")
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={settings.sql_server};"
        f"DATABASE={settings.sql_database};"
        f"UID={settings.sql_uid};"
        f"PWD={settings.sql_pwd};"
        "TrustServerCertificate=yes;"
    )


def fetch_active_leaves(settings: Settings) -> list[dict[str, Any]]:
    """
    Connect to SQL Server, run the maternity-leave query, return rows as dicts.
    Column names match SQL aliases: recurso_id, centro_costo, fecha_inicio, fecha_fin,
    and erp_maternidad_pry when MATERNITY_PRY_USE_CABIDRECURSO is on;
    recurso_display_name when SQL_COL_TIT_NOMBRE / SQL_COL_TIT_APELLIDO are set.

    If settings.sync_test_date is set, that date is used as the in-leave window
    (same calendar semantics as FechaDocumento for scope=today), not GETDATE().
    """
    conn_str = _build_connection_string(settings)
    rows: list[dict[str, Any]] = []
    as_of = settings.sync_test_date

    try:
        conn = pyodbc.connect(conn_str, timeout=SQL_LOGIN_TIMEOUT)
    except pyodbc.Error as e:
        logger.exception("SQL Server connection failed: %s", e)
        raise

    try:
        conn.timeout = SQL_QUERY_TIMEOUT
        cursor = conn.cursor()
        try:
            sql = build_active_maternity_leaves_sql(settings, as_of_calendar=as_of)
            logger.debug("Maternity leave SQL: %s", sql.strip())
            if settings.sql_require_trabajador_activo:
                if as_of is not None:
                    cursor.execute(sql, (as_of, settings.sql_trab_estado_activo))
                else:
                    cursor.execute(sql, (settings.sql_trab_estado_activo,))
            else:
                if as_of is not None:
                    cursor.execute(sql, (as_of,))
                else:
                    cursor.execute(sql)
            columns = [c[0] for c in cursor.description] if cursor.description else []
            for record in cursor.fetchall():
                row: dict[str, Any] = {}
                for i, col in enumerate(columns):
                    row[col] = record[i]
                rows.append(row)
        except pyodbc.Error as e:
            logger.exception("SQL query failed: %s", e)
            raise
        finally:
            cursor.close()
    finally:
        conn.close()

    if as_of is not None:
        logger.info(
            "Fetched %d maternity leave row(s) with leave window anchored on SYNC_TEST_DATE=%s.",
            len(rows),
            as_of.isoformat(),
        )
    else:
        logger.info("Fetched %d active maternity leave row(s)", len(rows))
    return rows


def fetch_holiday_dates_in_range(
    settings: Settings, range_start: date, range_end: date
) -> set[date]:
    """Dates in ct_RHFeriados within [range_start, range_end] inclusive."""
    conn_str = _build_connection_string(settings)
    sql = build_holiday_dates_in_range_sql(settings)
    out: set[date] = set()

    try:
        conn = pyodbc.connect(conn_str, timeout=SQL_LOGIN_TIMEOUT)
    except pyodbc.Error as e:
        logger.exception("SQL Server connection failed (holiday range): %s", e)
        raise

    try:
        conn.timeout = SQL_QUERY_TIMEOUT
        cursor = conn.cursor()
        try:
            logger.debug(
                "Holiday range SQL: %s | %s..%s", sql.strip(), range_start, range_end
            )
            cursor.execute(sql, (range_start, range_end))
            for (fer_day,) in cursor.fetchall():
                if fer_day is None:
                    continue
                out.add(
                    fer_day.date() if hasattr(fer_day, "date") else fer_day
                )
        except pyodbc.Error as e:
            logger.exception("Holiday range query failed: %s", e)
            raise
        finally:
            cursor.close()
    finally:
        conn.close()

    return out


def fetch_date_is_public_holiday(settings: Settings, d: date) -> bool:
    """
    True if d matches a row in ct_RHFeriados (same calendar date in sql_col_feriado_fecha).
    """
    conn_str = _build_connection_string(settings)
    sql = build_holiday_exists_sql(settings)

    try:
        conn = pyodbc.connect(conn_str, timeout=SQL_LOGIN_TIMEOUT)
    except pyodbc.Error as e:
        logger.exception("SQL Server connection failed (holiday check): %s", e)
        raise

    try:
        conn.timeout = SQL_QUERY_TIMEOUT
        cursor = conn.cursor()
        try:
            logger.debug("Holiday check SQL: %s | date=%s", sql.strip(), d)
            cursor.execute(sql, d)
            row = cursor.fetchone()
            return row is not None
        except pyodbc.Error as e:
            logger.exception("Holiday query failed: %s", e)
            raise
        finally:
            cursor.close()
    finally:
        conn.close()
