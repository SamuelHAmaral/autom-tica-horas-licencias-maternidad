"""Arma los datos de procesarAlta (TpryParteDiaGS) a partir de las filas SQL.

Nota: un parte por día hábil. main.py elige las fechas con NODUM_PARTE_SCOPE
(today/backfill = puesta al día hasta la fecha de corrida; week = semana ISO actual).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from src.settings import Settings

logger = logging.getLogger(__name__)


def _to_date(val: Any) -> date:
    """pyodbc devuelve datetime para columnas de fecha. Los textos se rechazan a propósito."""
    if val is None:
        raise ValueError("missing date value for leave bounds")
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    raise TypeError(f"expected date or datetime, got {type(val).__name__}")


def parse_leave_fecha_inicio(db_row: Mapping[str, Any]) -> date:
    """``fecha_inicio`` de una fila del extractor, como fecha de calendario."""
    return _to_date(db_row["fecha_inicio"])


def current_week_monday_sunday(today: date) -> tuple[date, date]:
    """Lunes a domingo de la semana ISO que contiene today."""
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def holiday_range_for_sync(
    parte_scope: str,
    rows: Sequence[Mapping[str, Any]],
    run_date: date,
) -> tuple[date, date]:
    """
    Límites inclusive para cargar ct_RHFeriados.

    Con ``today`` y ``backfill``, va desde el ``fecha_inicio`` más temprano de las filas
    hasta ``run_date``, para poder contrastar los días de la puesta al día con los feriados.
    """
    if parte_scope in ("today", "backfill"):
        if not rows:
            return run_date, run_date
        earliest = min(_to_date(r["fecha_inicio"]) for r in rows)
        return earliest, run_date
    mon, sun = current_week_monday_sunday(run_date)
    return mon, sun


def leave_working_dates_backfill_to_run_date(
    db_row: Mapping[str, Any],
    holiday_dates: set[date],
    *,
    run_date: date | None = None,
) -> list[date]:
    """
    Días lunes a viernes desde ``fecha_inicio`` hasta ``min(fecha_fin, run_date)``, sin feriados.

    Sirve cuando la fila aparece en RRHH después del inicio real: entran todos los días
    hábiles desde el inicio verdadero hasta la fecha de corrida, no solo la semana ISO actual.
    """
    run_date = run_date or date.today()
    fi = _to_date(db_row["fecha_inicio"])
    ff = _to_date(db_row["fecha_fin"])
    lo, hi = fi, min(ff, run_date)
    if lo > hi:
        return []

    out: list[date] = []
    d = lo
    while d <= hi:
        if d.weekday() < 5 and d not in holiday_dates:
            out.append(d)
        d += timedelta(days=1)
    return out


def leave_working_dates_in_current_week(
    db_row: Mapping[str, Any],
    holiday_dates: set[date],
    *,
    today: date | None = None,
) -> list[date]:
    """
    Días lunes a viernes de la semana ISO de `today` que caen dentro de [fecha_inicio, fecha_fin]
    y no están en holiday_dates (ct_RHFeriados de esa semana).
    """
    today = today or date.today()
    mon, sun = current_week_monday_sunday(today)
    fi = _to_date(db_row["fecha_inicio"])
    ff = _to_date(db_row["fecha_fin"])
    lo = max(mon, fi)
    hi = min(sun, ff)
    if lo > hi:
        return []

    out: list[date] = []
    d = lo
    while d <= hi:
        if d.weekday() < 5 and d not in holiday_dates:
            out.append(d)
        d += timedelta(days=1)
    return out


def _erp_maternidad_pry_stripped(db_row: Mapping[str, Any]) -> str | None:
    """Escalar de la subconsulta del extractor (el controlador puede cambiar las mayúsculas del alias)."""
    for key in ("erp_maternidad_pry", "ERP_MATERNIDAD_PRY"):
        v = db_row.get(key)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def resolve_g2_centrode_costo(db_row: Mapping[str, Any], settings: Settings) -> str:
    """
    Nodum G2.CentrodeCosto = código de proyecto.

    Primero ``erp_maternidad_pry`` del ERP (``ct_cabidrecursos`` → negocio → proyecto cuyo
    nombre contiene ``maternidad``), la misma regla que la pantalla de Nodum cuando
    MATERNITY_PRY_USE_CABIDRECURSO está activo.

    Si no, usa ``centro_costo`` (``SQL_COL_TRAB_CENTRO_COSTO``, p. ej. cod_dpto) contra
    ``settings.nodum_maternity_project_by_dept`` (sin distinguir mayúsculas); después
    ``NODUM_G2_CENTRODECOSTO``; si tampoco hay, el valor crudo de SQL (comportamiento viejo).
    """
    erp_pry = _erp_maternidad_pry_stripped(db_row)
    if erp_pry and settings.maternity_pry_use_cabidrecurso:
        logger.info(
            "G2.CentrodeCosto=%r from ERP maternidad proyecto (ct_cabidrecursos; recurso_id=%r)",
            erp_pry,
            str(db_row.get("recurso_id", "")).strip(),
        )
        return erp_pry

    dept_raw = db_row.get("centro_costo")
    dept_key = str(dept_raw).strip().casefold() if dept_raw is not None else ""
    m = settings.nodum_maternity_project_by_dept
    if dept_key and m:
        mapped = m.get(dept_key)
        if mapped:
            cc = mapped.strip()
            logger.info(
                "G2.CentrodeCosto=%r from NODUM_MATERNITY_PROJECT_BY_DEPT (SQL dept %r)",
                cc,
                str(dept_raw).strip() if dept_raw is not None else "",
            )
            return cc
    fallback = settings.nodum_g2_centrode_costo.strip()
    if fallback:
        logger.info(
            "G2.CentrodeCosto=%r default NODUM_G2_CENTRODECOSTO (SQL dept %r not in map)",
            fallback,
            str(dept_raw).strip() if dept_raw is not None else "",
        )
        return fallback
    return str(dept_raw).strip() if dept_raw is not None else ""


def build_daily_payloads(
    db_row: Mapping[str, Any],
    settings: Settings,
    dias_habiles: Sequence[date],
    *,
    hours_by_date: Mapping[date, float] | None = None,
) -> list[dict[str, Any]]:
    """
    Un dict TpryParteDiaGS por día: G1.FechaDocumento = ese día, G2 Horasdeduracion = las horas del día.
    """
    recurso_id = db_row["recurso_id"]
    cc_soap = resolve_g2_centrode_costo(db_row, settings)

    fmt = settings.nodum_fecha_documento_strftime
    payloads: list[dict[str, Any]] = []
    for dia in dias_habiles:
        horas = float(settings.nodum_g2_horas)
        if hours_by_date is not None and dia in hours_by_date:
            horas = float(hours_by_date[dia])
        g2_line: dict[str, Any] = {
            "CentrodeCosto": cc_soap,
            "CodigodeActividad": settings.nodum_g2_codigo_actividad,
            "Horasdeduracion": horas,
        }
        o2 = settings.nodum_g2_observaciones_1.strip()
        if o2:
            g2_line["observaciones_1"] = o2
        payloads.append(
            {
                "General": {
                    "G1": {
                        "CodigoEmpresa": settings.nodum_codigo_empresa,
                        "FechaDocumento": dia.strftime(fmt),
                        "CodigoIdentificacion": str(recurso_id).strip(),
                        "observaciones": settings.nodum_g1_observaciones,
                    },
                    "G2": [g2_line],
                }
            }
        )
    return payloads
