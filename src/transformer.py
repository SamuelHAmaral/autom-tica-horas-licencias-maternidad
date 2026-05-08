"""Map SQL rows to Nodum procesarAlta payloads (TpryParteDiaGS): one SOAP call per date in dias_habiles.

Which dates are passed in is controlled by NODUM_PARTE_SCOPE in main (today, week, or backfill).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from src.settings import Settings

logger = logging.getLogger(__name__)


def _to_date(val: Any) -> date:
    if val is None:
        raise ValueError("missing date value for leave bounds")
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    raise TypeError(f"expected date or datetime, got {type(val).__name__}")


def parse_leave_fecha_inicio(db_row: Mapping[str, Any]) -> date:
    """``fecha_inicio`` from an extractor row as a calendar date."""
    return _to_date(db_row["fecha_inicio"])


def current_week_monday_sunday(today: date) -> tuple[date, date]:
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def holiday_range_for_sync(
    parte_scope: str,
    rows: Sequence[Mapping[str, Any]],
    run_date: date,
) -> tuple[date, date]:
    """
    Inclusive calendar bounds for loading ct_RHFeriados.

    For ``backfill``, span from the earliest ``fecha_inicio`` among rows through ``run_date``
    so every candidate leave day can be checked against holidays.
    """
    if parte_scope == "backfill":
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
    Mon–Fri dates from ``fecha_inicio`` through ``min(fecha_fin, run_date)``, excluding holidays.

    Use when the leave row appears in HR after real-world start: every working day from true
    start through the run date is included (not only the current ISO week).
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
    Mon–Fri dates in the ISO week of `today` that fall inside [fecha_inicio, fecha_fin]
    and are not in holiday_dates (ct_RHFeriados for that week).
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
    """Scalar from extractor subquery (driver may vary alias casing)."""
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
    Nodum G2.CentrodeCosto = código proyecto.

    Prefer ``erp_maternidad_pry`` from ERP (``ct_cabidrecursos`` → negocio → proyecto whose name
    contains ``maternidad``), same rule as Nodum UI when MATERNITY_PRY_USE_CABIDRECURSO is on.

    Otherwise uses ``centro_costo`` (``SQL_COL_TRAB_CENTRO_COSTO``, e.g. cod_dpto) against
    ``settings.nodum_maternity_project_by_dept`` (case-insensitive); then ``NODUM_G2_CENTRODECOSTO``;
    else raw SQL value (legacy).
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
    One TpryParteDiaGS dict per calendar day: G1.FechaDocumento = that day, G2 Horasdeduracion = daily hours.
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
                        "CodigoEmpresa": "01",
                        "FechaDocumento": dia.strftime(fmt),
                        "CodigoIdentificacion": str(recurso_id).strip(),
                        "observaciones": settings.nodum_g1_observaciones,
                    },
                    "G2": [g2_line],
                }
            }
        )
    return payloads
