"""SOAP client for Nodum procesarAlta (zeep + HTTP Basic Auth)."""

from __future__ import annotations

import logging
import pprint
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from requests import Session
from requests.auth import HTTPBasicAuth
from requests.exceptions import RequestException
from zeep import Client
from zeep.exceptions import Error as ZeepError
from zeep.exceptions import Fault, TransportError
from zeep.helpers import serialize_object
from zeep.transports import Transport

from src.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcesarAltaResult:
    """SOAP procesarAlta outcome (dry run: both None)."""

    estado: int | None
    mensaje: str | None


def _unwrap_nodum_resultado_block(response: Any) -> Any | None:
    """Resolve list-of-one / Resultado wrapper to the object that carries estado/mensaje."""
    if response is None:
        return None
    if isinstance(response, list):
        if not response:
            return None
        response = response[0]
    resultado = getattr(response, "Resultado", None)
    if resultado is None and isinstance(response, dict):
        resultado = response.get("Resultado")
    if resultado is None:
        resultado = response
    return resultado


def _soap_timeout_tuple(settings: Settings) -> tuple[int, int]:
    return (
        settings.nodum_soap_connect_timeout,
        settings.nodum_soap_read_timeout,
    )


def _build_client(settings: Settings) -> Client:
    session = Session()
    session.auth = HTTPBasicAuth(settings.nodum_username, settings.nodum_password)
    transport = Transport(session=session, timeout=_soap_timeout_tuple(settings))
    return Client(wsdl=settings.nodum_wsdl, transport=transport)


def _build_read_client(settings: Settings) -> Client:
    wsdl = settings.nodum_read_wsdl.strip() or settings.nodum_wsdl
    read_user = settings.nodum_read_username.strip() or settings.nodum_username
    read_pwd = settings.nodum_read_password.strip() or settings.nodum_password
    session = Session()
    session.auth = HTTPBasicAuth(read_user, read_pwd)
    transport = Transport(session=session, timeout=_soap_timeout_tuple(settings))
    return Client(wsdl=wsdl, transport=transport)


def nodum_read_is_configured(settings: Settings) -> bool:
    return bool(settings.nodum_read_operation.strip())


def _dict_get_ci(d: Mapping[str, Any], key: str) -> Any:
    if not key:
        return None
    if key in d:
        return d.get(key)
    low = key.casefold()
    for k, v in d.items():
        if str(k).casefold() == low:
            return v
    return None


def _to_iso_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    if len(s) >= 10:
        head = s[:10]
        try:
            return date.fromisoformat(head)
        except ValueError:
            return None
    return None


def _walk_dicts(node: Any) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    if isinstance(node, Mapping):
        out.append(node)
        for v in node.values():
            out.extend(_walk_dicts(v))
    elif isinstance(node, list):
        for item in node:
            out.extend(_walk_dicts(item))
    return out


def fetch_existing_hours_by_date(
    settings: Settings,
    *,
    recurso_id: object,
    start_date: date,
    end_date: date,
) -> dict[date, float]:
    """
    Query Nodum read operation and aggregate already loaded hours per date for one recurso.
    Empty dict when read integration is not configured.
    """
    if not nodum_read_is_configured(settings):
        return {}
    client = _build_read_client(settings)
    op = settings.nodum_read_operation.strip()
    fecha_fmt = settings.nodum_fecha_documento_strftime
    kwargs = {
        settings.nodum_read_param_recurso: str(recurso_id).strip(),
        settings.nodum_read_param_fecha_desde: start_date.strftime(fecha_fmt),
        settings.nodum_read_param_fecha_hasta: end_date.strftime(fecha_fmt),
    }
    try:
        response = getattr(client.service, op)(**kwargs)
    except TypeError:
        nested = {
            "General": {
                "frmBloque1": {
                    settings.nodum_read_param_recurso: str(recurso_id).strip(),
                    settings.nodum_read_param_fecha_desde: start_date.strftime(fecha_fmt),
                    settings.nodum_read_param_fecha_hasta: end_date.strftime(fecha_fmt),
                }
            }
        }
        response = getattr(client.service, op)(
            **{settings.nodum_read_request_root: [nested]}
        )
    except (AttributeError, Fault, TransportError, RequestException, ZeepError) as e:
        logger.exception("Nodum read operation failed (%s): %s", op, e)
        raise

    payload = serialize_object(response)
    dicts = _walk_dicts(payload)
    recurso_expected = str(recurso_id).strip()
    filter_act = settings.nodum_read_filter_codigo_actividad.strip()
    filter_cc = settings.nodum_read_filter_centro_costo.strip()

    totals: dict[date, float] = {}
    for item in dicts:
        rec = _dict_get_ci(item, settings.nodum_read_recurso_key)
        fec = _dict_get_ci(item, settings.nodum_read_fecha_key)
        hrs = _dict_get_ci(item, settings.nodum_read_horas_key)
        if fec is None or hrs is None:
            continue
        if rec is not None and str(rec).strip() != recurso_expected:
            continue
        if filter_act:
            act = _dict_get_ci(item, settings.nodum_read_codigo_actividad_key)
            if str(act).strip() != filter_act:
                continue
        if filter_cc:
            cc = _dict_get_ci(item, settings.nodum_read_centro_costo_key)
            if str(cc).strip() != filter_cc:
                continue
        d = _to_iso_date(fec)
        if d is None or d < start_date or d > end_date:
            continue
        try:
            h = float(str(hrs).replace(",", "."))
        except ValueError:
            continue
        if h <= 0:
            continue
        totals[d] = totals.get(d, 0.0) + h
    return totals


def extract_estado_from_resultado(response: Any) -> int | None:
    """
    Walk zeep response for Resultado.estado (or Resultado['estado']).
    Nodum may return a one-element list of dicts instead of a Resultado wrapper.
    Returns None if not found or not convertible to int.
    """
    resultado = _unwrap_nodum_resultado_block(response)
    if resultado is None:
        return None
    estado = getattr(resultado, "estado", None)
    if estado is None and isinstance(resultado, dict):
        estado = resultado.get("estado")
    if estado is None:
        return None
    try:
        return int(estado)
    except (TypeError, ValueError):
        return None


def _log_dry_run_form_preview(
    tpry_parte_dia_gs: dict[str, Any],
    *,
    dry_run_context: Mapping[str, Any] | None = None,
) -> None:
    """
    Log human-readable fields that mirror what operators enter in Nodum (TpryParteDiaGS).
    Same handlers as the rest of the job (console: optional color; file: UTF-8 plain text).
    """
    try:
        gen = tpry_parte_dia_gs.get("General")
        if not isinstance(gen, dict):
            gen = {}
        g1 = gen.get("G1")
        if not isinstance(g1, dict):
            g1 = {}
        g2_raw = gen.get("G2")
        if isinstance(g2_raw, dict):
            g2_list = [g2_raw]
        elif isinstance(g2_raw, list):
            g2_list = g2_raw
        else:
            g2_list = []
    except (AttributeError, TypeError):
        logger.warning("Dry run: forma de payload inesperada; no se arma vista de formulario.")
        return

    ctx = dict(dry_run_context) if dry_run_context else {}

    lines: list[str] = [
        "Dry run — datos equivalentes al formulario (TpryParteDiaGS); no se llama a Nodum:",
        f"  Empresa (G1.CodigoEmpresa): {g1.get('CodigoEmpresa', '')!s}",
        f"  Fecha documento (G1.FechaDocumento): {g1.get('FechaDocumento', '')!s}",
        f"  Recurso / código identificación (G1.CodigoIdentificacion): "
        f"{g1.get('CodigoIdentificacion', '')!s}",
    ]
    dn = ctx.get("recurso_display_name")
    if dn is not None and str(dn).strip():
        lines.append(f"  Nombre titular (RRHH): {str(dn).strip()!s}")
    hr_d = ctx.get("hr_cod_dpto")
    if hr_d is not None and str(hr_d).strip():
        lines.append(f"  Código dpto legajo (SQL): {str(hr_d).strip()!s}")
    erp_p = ctx.get("erp_maternidad_pry")
    if erp_p is not None and str(erp_p).strip():
        lines.append(f"  Proyecto maternidad (ERP / subconsulta): {str(erp_p).strip()!s}")

    obs = g1.get("observaciones")
    if obs is not None and str(obs).strip():
        lines.append(f"  Observaciones cabecera (G1): {obs!s}")

    if not g2_list:
        lines.append("  (Sin líneas G2 en el payload)")
    for i, g2 in enumerate(g2_list, start=1):
        if not isinstance(g2, dict):
            lines.append(f"  Línea G2 #{i}: (formato no dict, omitida)")
            continue
        lines.append(
            f"  Línea G2 #{i} — Proyecto / centro de costo (CentrodeCosto): "
            f"{g2.get('CentrodeCosto', '')!s}"
        )
        lines.append(
            f"  Línea G2 #{i} — Código actividad (CodigodeActividad): "
            f"{g2.get('CodigodeActividad', '')!s}"
        )
        lines.append(
            f"  Línea G2 #{i} — Horas (Horasdeduracion): {g2.get('Horasdeduracion', '')!s}"
        )
        o2 = g2.get("observaciones_1")
        if o2 is not None and str(o2).strip():
            lines.append(f"  Línea G2 #{i} — Observaciones línea: {o2!s}")

    logger.info("\n".join(lines))


def extract_mensaje_from_resultado(response: Any) -> str | None:
    resultado = _unwrap_nodum_resultado_block(response)
    if resultado is None:
        return None
    mensaje = getattr(resultado, "mensaje", None)
    if mensaje is None and isinstance(resultado, dict):
        mensaje = resultado.get("mensaje")
    if mensaje is None:
        return None
    s = str(mensaje).strip()
    return s if s else None


def procesar_alta(
    settings: Settings,
    tpry_parte_dia_gs: dict[str, Any],
    *,
    dry_run_context: Mapping[str, Any] | None = None,
) -> ProcesarAltaResult:
    """
    Invoke procesarAlta with TpryParteDiaGS payload.
    NODUM_DRY_RUN=1: log form-style preview + print payload (no network);
    returns ProcesarAltaResult(None, None).
    """
    if settings.nodum_dry_run:
        _log_dry_run_form_preview(tpry_parte_dia_gs, dry_run_context=dry_run_context)
        print("--- TpryParteDiaGS payload (dry run, técnico) ---")
        pprint.pprint(tpry_parte_dia_gs, width=100, sort_dicts=False)
        logger.info(
            "Dry run: vista de formulario arriba; dict técnico en consola. "
            "SOAP no llamado (timeouts serían connect=%ss read=%ss).",
            settings.nodum_soap_connect_timeout,
            settings.nodum_soap_read_timeout,
        )
        return ProcesarAltaResult(None, None)

    client = _build_client(settings)
    try:
        response = client.service.procesarAlta(TpryParteDiaGS=tpry_parte_dia_gs)
    except Fault as e:
        logger.exception("SOAP Fault from procesarAlta: %s", e)
        raise
    except TransportError as e:
        logger.exception("SOAP transport error: %s", e)
        raise
    except (RequestException, ZeepError) as e:
        logger.exception("Unexpected SOAP/request error calling procesarAlta: %s", e)
        raise

    estado = extract_estado_from_resultado(response)
    mensaje = extract_mensaje_from_resultado(response)
    if estado is None:
        logger.warning(
            "procesarAlta returned no parseable estado; raw response: %r", response
        )
    return ProcesarAltaResult(estado=estado, mensaje=mensaje)
