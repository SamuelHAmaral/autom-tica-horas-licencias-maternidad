"""
Entry point: extract active maternity leaves, transform for Nodum, call procesarAlta.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Any

import pyodbc
from dotenv import load_dotenv
from requests.exceptions import RequestException
from zeep.exceptions import Error as ZeepError

from src import backfill_state
from src.calendar_gate import should_run_sync
from src.extractor import fetch_active_leaves, fetch_holiday_dates_in_range
from src.loader import fetch_existing_hours_by_date, nodum_read_is_configured, procesar_alta
from src.logging_config import LOG_FILENAME, setup_logging
from src.production_checks import log_production_checks, run_production_checks
from src.settings import Settings, load_settings
from src.transformer import (
    build_daily_payloads,
    holiday_range_for_sync,
    leave_working_dates_backfill_to_run_date,
    leave_working_dates_in_current_week,
    parse_leave_fecha_inicio,
    resolve_g2_centrode_costo,
)

logger = logging.getLogger(__name__)


def _row_keys_lower(row: dict[str, Any]) -> dict[str, Any]:
    return {str(k).lower(): v for k, v in row.items()}


def _row_get_ci(row: Mapping[str, Any], *names: str) -> Any:
    low = _row_keys_lower(dict(row))
    for n in names:
        v = low.get(n.lower())
        if v is not None:
            return v
    for n in names:
        if n in row:
            return row[n]
    return None


def _nombre_suffix(row: Mapping[str, Any]) -> str:
    """Append to log lines when SQL exposes recurso_display_name."""
    name = _row_get_ci(row, "recurso_display_name")
    if name is None or not str(name).strip():
        return ""
    return f" nombre={str(name).strip()!r}"


def _dry_run_context_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Extra fields for dry-run log (nombre, HR dpto, ERP PRY)."""
    ctx: dict[str, Any] = {}
    name = _row_get_ci(row, "recurso_display_name")
    if name is not None and str(name).strip():
        ctx["recurso_display_name"] = str(name).strip()
    cc = row.get("centro_costo")
    if cc is not None and str(cc).strip():
        ctx["hr_cod_dpto"] = str(cc).strip()
    erp = _row_get_ci(row, "erp_maternidad_pry", "ERP_MATERNIDAD_PRY")
    if erp is not None and str(erp).strip():
        ctx["erp_maternidad_pry"] = str(erp).strip()
    return ctx


def _nodum_mensaje_is_duplicate_ok(mensaje: str | None, settings: Settings) -> bool:
    if not settings.nodum_duplicate_ok_substrings:
        return False
    m = (mensaje or "").lower()
    return any(s in m for s in settings.nodum_duplicate_ok_substrings)

def main() -> int:
    BASE_DIR = Path(__file__).resolve().parent
    env_path = BASE_DIR / ".env"
    if not env_path.is_file():
        print(
            f"Missing .env at {env_path}. Copy .env.example to .env and fill in values.",
            file=sys.stderr,
        )
        return 1
    if env_path.stat().st_size == 0:
        print(
            f".env is empty ({env_path}). Paste your variables from .env.example, save the file (Ctrl+S), then run again.",
            file=sys.stderr,
        )
        return 1

    # utf-8-sig strips BOM; stream + override=True so .env wins over stale process env
    text = env_path.read_text(encoding="utf-8-sig")
    loaded = load_dotenv(stream=StringIO(text), override=True)
    setup_logging()
    logger.info("Log file (rotating): %s", BASE_DIR / LOG_FILENAME)
    if not loaded:
        logger.warning(
            "No variables were loaded from .env (wrong encoding or no KEY=value lines). Path: %s",
            env_path,
        )

    try:
        settings = load_settings()
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        return 1

    strict_prod = os.environ.get("SYNC_PRODUCTION", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if strict_prod:
        logger.info("SYNC_PRODUCTION=1: strict pre-flight checks enabled.")
    prod = run_production_checks(settings, strict=strict_prod)
    log_production_checks(prod)
    if not prod.ok:
        logger.error(
            "Aborting: fix blocking production checks or unset SYNC_PRODUCTION for a dry test."
        )
        return 1

    if settings.sync_force_run:
        logger.warning(
            "SYNC_FORCE_RUN is set; weekend and ct_RHFeriados checks are disabled."
        )

    run_date = settings.sync_test_date or date.today()
    if settings.sync_test_date is not None:
        logger.warning(
            "SYNC_TEST_DATE=%s is set: using it as the calendar day for gate, ISO week, "
            "NODUM_PARTE_SCOPE=today, and the SQL leave window (replaces GETDATE()). "
            "Remove SYNC_TEST_DATE from .env for production.",
            run_date.isoformat(),
        )

    if not settings.nodum_dry_run:
        logger.warning(
            "NODUM_DRY_RUN is off; procesarAlta will call Nodum (SOAP timeouts "
            "connect=%ss read=%ss).",
            settings.nodum_soap_connect_timeout,
            settings.nodum_soap_read_timeout,
        )

    _scope_desc = {
        "today": "submit at most one parte per recurso for the run date only",
        "week": "submit partes for every working leave day in the current ISO week (intersect leave)",
        "backfill": "submit partes for every working leave day from fecha_inicio through min(fecha_fin, run date)",
    }[settings.nodum_parte_scope]
    logger.info("NODUM_PARTE_SCOPE=%s: %s", settings.nodum_parte_scope, _scope_desc)
    logger.info("Nodum write (procesarAlta) WSDL: %s", settings.nodum_wsdl)
    if nodum_read_is_configured(settings):
        logger.info(
            "Nodum read enabled: operation=%s wsdl=%s",
            settings.nodum_read_operation,
            settings.nodum_read_wsdl or settings.nodum_wsdl,
        )
    else:
        logger.info(
            "Nodum read disabled: local sync state only (set NODUM_READ_OPERATION to enable)."
        )

    logger.info(
        "SQL column mapping (physical names): cpt_RHLicencias.%s / %s, ct_RHTrabajador.%s",
        settings.sql_col_lic_fecha_inicio,
        settings.sql_col_lic_fecha_fin,
        settings.sql_col_trab_centro_costo,
    )
    if settings.maternity_pry_use_cabidrecurso:
        logger.info(
            "G2.CentrodeCosto: prefer ERP [%s].ct_cabidrecursos -> proyecto maternidad; "
            "fallback NODUM_MATERNITY_PROJECT_BY_DEPT / NODUM_G2_CENTRODECOSTO.",
            settings.amaral_catalog_database,
        )
    else:
        logger.info(
            "G2.CentrodeCosto: MATERNITY_PRY_USE_CABIDRECURSO off; using HR dept map only."
        )
    if settings.sql_require_trabajador_activo:
        logger.info(
            "Active worker filter: ct_RHTrabajador.%s = %s",
            settings.sql_col_trab_estado,
            settings.sql_trab_estado_activo,
        )

    run_ok, skip_reason = should_run_sync(settings, today=run_date)
    if not run_ok:
        logger.info("Skipping run: %s.", skip_reason)
        return 0

    try:
        rows = fetch_active_leaves(settings)
    except pyodbc.Error:
        logger.critical(
            "CRITICAL: SQL extraction failed; aborting with exit code 2. "
            "Could not read active maternity leaves from SQL Server.",
            exc_info=True,
        )
        return 2

    if not rows:
        logger.info("No active maternity leaves to process.")
        return 0

    cal_start, cal_end = holiday_range_for_sync(settings.nodum_parte_scope, rows, run_date)
    try:
        holiday_dates = fetch_holiday_dates_in_range(settings, cal_start, cal_end)
    except pyodbc.Error:
        logger.critical(
            "CRITICAL: Holiday range query failed; aborting with exit code 2. "
            "Could not load ct_RHFeriados for %s..%s.",
            cal_start.isoformat(),
            cal_end.isoformat(),
            exc_info=True,
        )
        return 2

    state_path: Path | None = None
    state_data: dict[str, Any] | None = None
    if not settings.nodum_backfill_state_disabled:
        state_path = BASE_DIR / settings.nodum_backfill_state_file
        state_data = backfill_state.load(state_path)
        logger.info("Sync state file: %s", state_path)
    if settings.nodum_parte_scope == "backfill":
        logger.info(
            "Backfill mode: ct_RHFeriados loaded for %s..%s (%d holiday date(s) in range).",
            cal_start.isoformat(),
            cal_end.isoformat(),
            len(holiday_dates),
        )
        if settings.nodum_backfill_state_disabled:
            logger.info(
                "Backfill watermark off (NODUM_BACKFILL_STATE_DISABLE); full range every run."
            )

    processed_recursos: set[object] = set()
    skipped_duplicates = 0
    failures = 0
    for i, row in enumerate(rows, start=1):
        nom = _nombre_suffix(row)
        recurso = row.get("recurso_id")
        if recurso in processed_recursos:
            skipped_duplicates += 1
            logger.warning(
                "Duplicate active leave row for recurso_id=%s (SQL row %d/%d). "
                "Skipping to avoid double-billing in Nodum.%s",
                recurso,
                i,
                len(rows),
                nom,
            )
            continue
        processed_recursos.add(recurso)

        if settings.nodum_parte_scope == "backfill":
            valid_dates = leave_working_dates_backfill_to_run_date(
                row, holiday_dates, run_date=run_date
            )
        else:
            valid_dates = leave_working_dates_in_current_week(
                row, holiday_dates, today=run_date
            )
            if settings.nodum_parte_scope == "today":
                valid_dates = [d for d in valid_dates if d == run_date]
        fi: date | None = None
        if settings.nodum_parte_scope == "backfill":
            fi = parse_leave_fecha_inicio(row)
            if state_path is not None and state_data is not None:
                last_ok = backfill_state.get_last_ok_fecha(
                    state_data, recurso, fi
                )
                n_before = len(valid_dates)
                valid_dates = backfill_state.dates_after_watermark(
                    valid_dates, last_ok
                )
                if last_ok is not None and len(valid_dates) < n_before:
                    logger.info(
                        "Backfill skip already-synced recurso_id=%s last_ok=%s "
                        "(%d pending weekday(s), %d skipped) SQL row %d/%d.%s",
                        recurso,
                        last_ok.isoformat(),
                        len(valid_dates),
                        n_before - len(valid_dates),
                        i,
                        len(rows),
                        nom,
                    )

        if not valid_dates:
            if settings.nodum_parte_scope == "today":
                logger.info(
                    "Skipping recurso_id=%s: no parte for run date %s (not a working leave day, "
                    "holiday, or outside leave range; SQL row %d/%d).%s",
                    recurso,
                    run_date.isoformat(),
                    i,
                    len(rows),
                    nom,
                )
            elif settings.nodum_parte_scope == "backfill":
                logger.info(
                    "Skipping recurso_id=%s: no working leave days from inicio through run date "
                    "(SQL row %d/%d).%s",
                    recurso,
                    i,
                    len(rows),
                    nom,
                )
            else:
                logger.info(
                    "Skipping recurso_id=%s: no working days in current week within leave "
                    "(SQL row %d/%d).%s",
                    recurso,
                    i,
                    len(rows),
                    nom,
                )
            continue

        dry_ctx = _dry_run_context_from_row(row) if settings.nodum_dry_run else None
        target_daily_hours = float(settings.nodum_g2_horas)
        g2_cc = resolve_g2_centrode_costo(row, settings)
        nodum_loaded_by_date: dict[date, float] = {}
        if nodum_read_is_configured(settings):
            try:
                nodum_loaded_by_date = fetch_existing_hours_by_date(
                    settings,
                    recurso_id=recurso,
                    start_date=min(valid_dates),
                    end_date=max(valid_dates),
                    g2_centrode_costo=g2_cc,
                )
            except Exception:
                failures += 1
                logger.critical(
                    "CRITICAL: Nodum read failed row %d/%d recurso_id=%s "
                    "range=%s..%s%s",
                    i,
                    len(rows),
                    recurso,
                    min(valid_dates).isoformat(),
                    max(valid_dates).isoformat(),
                    nom,
                    exc_info=True,
                )
                continue
        pending_dates: list[date] = []
        pending_hours_by_date: dict[date, float] = {}
        for dia in valid_dates:
            already_local = (
                backfill_state.get_recorded_hours(state_data, recurso, dia)
                if state_data is not None
                else 0.0
            )
            already_nodum = nodum_loaded_by_date.get(dia, 0.0)
            already = max(already_local, already_nodum)
            missing = max(0.0, target_daily_hours - already)
            if missing <= 1e-9:
                logger.info(
                    "Skipping recurso_id=%s FechaDocumento=%s: already complete "
                    "(%.2f/%.2f h; local=%.2f nodum=%.2f).%s",
                    recurso,
                    dia.isoformat(),
                    already,
                    target_daily_hours,
                    already_local,
                    already_nodum,
                    nom,
                )
                continue
            pending_dates.append(dia)
            pending_hours_by_date[dia] = missing

        if not pending_dates:
            continue

        daily_payloads = build_daily_payloads(
            row, settings, pending_dates, hours_by_date=pending_hours_by_date
        )
        state_dirty = False
        for dia, payload in zip(pending_dates, daily_payloads):
            fecha_doc = payload["General"]["G1"]["FechaDocumento"]
            try:
                result = procesar_alta(
                    settings, payload, dry_run_context=dry_ctx
                )
            except (ZeepError, RequestException):
                failures += 1
                logger.critical(
                    "CRITICAL: Nodum load failed (procesarAlta) row %d/%d recurso_id=%s "
                    "FechaDocumento=%s%s",
                    i,
                    len(rows),
                    recurso,
                    fecha_doc,
                    nom,
                    exc_info=True,
                )
                continue

            if settings.nodum_dry_run:
                name_bit = ""
                if dry_ctx and dry_ctx.get("recurso_display_name"):
                    name_bit = f" nombre={dry_ctx['recurso_display_name']!r}"
                horas_envio = pending_hours_by_date.get(dia, target_daily_hours)
                logger.info(
                    "Row %d/%d dry run recurso_id=%s%s FechaDocumento=%s Horasdeduracion=%.2f",
                    i,
                    len(rows),
                    recurso,
                    name_bit,
                    fecha_doc,
                    horas_envio,
                )
                continue

            ok_for_state = False
            if result.estado is None:
                failures += 1
                logger.critical(
                    "CRITICAL: Nodum response missing parseable estado row %d/%d "
                    "recurso_id=%s FechaDocumento=%s (exit 3 if any persist).%s",
                    i,
                    len(rows),
                    recurso,
                    fecha_doc,
                    nom,
                )
            elif result.estado != 0:
                if _nodum_mensaje_is_duplicate_ok(result.mensaje, settings):
                    logger.info(
                        "Row %d/%d Nodum estado=%s treated as duplicate/non-fatal "
                        "recurso_id=%s FechaDocumento=%s mensaje=%s%s",
                        i,
                        len(rows),
                        result.estado,
                        recurso,
                        fecha_doc,
                        result.mensaje or "",
                        nom,
                    )
                    ok_for_state = True
                    if state_data is not None:
                        backfill_state.mark_day_full(
                            state_data, recurso, dia, target_daily_hours
                        )
                        state_dirty = True
                else:
                    failures += 1
                    logger.critical(
                        "CRITICAL: Nodum rejected load estado=%s mensaje=%r row %d/%d "
                        "recurso_id=%s FechaDocumento=%s%s",
                        result.estado,
                        result.mensaje or "",
                        i,
                        len(rows),
                        recurso,
                        fecha_doc,
                        nom,
                    )
            else:
                logger.info(
                    "Row %d/%d OK recurso_id=%s FechaDocumento=%s estado=0 mensaje=%s%s",
                    i,
                    len(rows),
                    recurso,
                    fecha_doc,
                    result.mensaje or "",
                    nom,
                )
                ok_for_state = True

            if (
                ok_for_state
                and state_path is not None
                and state_data is not None
            ):
                backfill_state.record_hours(
                    state_data, recurso, dia, pending_hours_by_date.get(dia, 0.0)
                )
                if fi is not None:
                    backfill_state.record_day_ok(state_data, recurso, fi, dia)
                state_dirty = True

        if state_dirty and state_path is not None and state_data is not None:
            backfill_state.save(state_path, state_data)

    if failures:
        logger.critical(
            "CRITICAL: Run finished with %d Nodum/load failure(s); exiting with code 3. "
            "SQL rows=%d, duplicate SQL rows skipped=%d.",
            failures,
            len(rows),
            skipped_duplicates,
        )
        return 3

    if skipped_duplicates:
        logger.info(
            "Processed %d unique recurso(s); skipped %d duplicate SQL row(s).",
            len(processed_recursos),
            skipped_duplicates,
        )
    else:
        logger.info("All %d row(s) processed successfully.", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
