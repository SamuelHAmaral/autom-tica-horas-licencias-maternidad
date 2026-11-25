"""Carga la configuración desde el entorno. Los secretos quedan en .env.

Nota: un valor en blanco no siempre es el valor por defecto. opt() usa el valor por defecto si
falta o está vacío. from_env_str() conserva el blanco cuando la clave está definida.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_CATALOG_DB_SAFE = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class Settings:
    # Conexión y nombres físicos opcionales de columnas de RRHH (ver .env.example).
    sql_driver: str
    sql_server: str
    sql_database: str
    sql_uid: str
    sql_pwd: str
    # Ajuste TLS de ODBC (Encrypt vacío = comportamiento del controlador).
    sql_encrypt: str
    sql_trust_server_certificate: bool
    sql_col_lic_fecha_inicio: str
    sql_col_lic_fecha_fin: str
    sql_col_trab_centro_costo: str
    # Columnas opcionales de ct_titulares para el log y la prueba en seco: recurso_display_name en el extract.
    sql_col_tit_nombre: str
    sql_col_tit_apellido: str
    sql_col_trab_estado: str
    sql_trab_estado_activo: str
    sql_require_trabajador_activo: bool
    nodum_wsdl: str
    nodum_username: str
    nodum_password: str
    nodum_read_username: str
    nodum_read_password: str
    nodum_read_wsdl: str
    nodum_read_operation: str
    nodum_read_param_recurso: str
    nodum_read_param_fecha_desde: str
    nodum_read_param_fecha_hasta: str
    nodum_read_request_root: str
    nodum_read_recurso_key: str
    nodum_read_fecha_key: str
    nodum_read_horas_key: str
    nodum_read_codigo_actividad_key: str
    nodum_read_centro_costo_key: str
    nodum_read_filter_codigo_actividad: str
    nodum_read_filter_centro_costo: str
    # Si es verdadero, solo suma líneas cuyo texto de centro o actividad coincide con el proyecto G2 resuelto (o el texto de respaldo).
    nodum_read_match_resolved_proyecto: bool
    # Sin distinguir mayúsculas: coincide si este texto aparece en centro o actividad (p. ej. maternidad). Vacío = sin respaldo.
    nodum_read_line_substring_fallback: str
    # Forma del parte TpryParteDiaGS (alinear las claves con el WSDL si zeep rechaza un campo).
    nodum_fecha_documento_strftime: str
    nodum_codigo_empresa: str
    nodum_g1_observaciones: str
    nodum_g2_codigo_actividad: str
    nodum_g2_horas: float
    # today | week | backfill — ver NODUM_PARTE_SCOPE en .env.example.
    nodum_parte_scope: str
    nodum_dry_run: bool
    nodum_soap_connect_timeout: int
    nodum_soap_read_timeout: int
    # Si Nodum devuelve estado != 0 pero el mensaje contiene alguno de estos (sin distinguir mayúsculas), solo se registra INFO (no es fallo).
    # Variable ausente → frases en español por defecto. Variable presente pero vacía → estricto (sin excepciones por texto).
    nodum_duplicate_ok_substrings: tuple[str, ...]
    # G2.CentrodeCosto en el WSDL = código de proyecto (p. ej. PRY00380). Respaldo si el departamento no está en el mapa.
    nodum_g2_centrode_costo: str
    # Código de departamento SQL (recortado, sin distinguir mayúsculas) → proyecto Nodum de G2.CentrodeCosto. Sale de NODUM_MATERNITY_PROJECT_BY_DEPT.
    nodum_maternity_project_by_dept: dict[str, str]
    # G2.observaciones_1 opcional; vacío → omitir clave en el dict.
    nodum_g2_observaciones_1: str
    # Día laborable: columna de fecha en ct_RHFeriados (identificador SQL simple).
    sql_col_feriado_fecha: str
    # Si true, no aplica fin de semana ni feriados (pruebas / corrida manual).
    sync_force_run: bool
    # Solo pruebas: si está definido, reemplaza date.today() en calendario, semana ISO y NODUM_PARTE_SCOPE=today.
    sync_test_date: date | None
    # Base del catálogo ERP en el mismo SQL Server (amaral01): recurso → ct_cabidrecursos → proyecto maternidad PRY.
    amaral_catalog_database: str
    maternity_pry_use_cabidrecurso: bool
    # backfill: marcas de agua JSON (por recurso + fec_inicio) para no reenviar todos los días en cada corrida.
    nodum_backfill_state_disabled: bool
    nodum_backfill_state_file: str


def load_settings() -> Settings:
    """Arma Settings desde el entorno del proceso. ValueError si un valor es inválido."""

    # --- Lectores de variables ---
    # opt: si falta o está en blanco, usa el valor por defecto.
    # from_env_str: si la clave está y el valor es blanco, queda en blanco (lo dejaron así a propósito).
    def req(name: str) -> str:
        v = os.environ.get(name, "").strip()
        if not v:
            raise ValueError(f"Missing or empty required environment variable: {name}")
        return v

    def opt(name: str, default: str) -> str:
        v = os.environ.get(name, "").strip()
        return v if v else default

    def opt_float(name: str, default: float) -> float:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return default
        return float(raw.replace(",", "."))

    fmt = opt("NODUM_FECHA_DOCUMENTO_STRFTIME", "%Y-%m-%d")
    try:
        date.today().strftime(fmt)
    except ValueError as e:
        raise ValueError(
            f"Invalid NODUM_FECHA_DOCUMENTO_STRFTIME={fmt!r}: {e}"
        ) from e

    def from_env_str(name: str, default: str) -> str:
        if name not in os.environ:
            return default
        return os.environ.get(name, "").strip()

    def from_env_optional(name: str) -> str:
        if name not in os.environ:
            return ""
        return os.environ.get(name, "").strip()

    def env_truthy(name: str) -> bool:
        v = os.environ.get(name, "").strip().lower()
        return v in ("1", "true", "yes", "on")

    def opt_bool(name: str, default: bool) -> bool:
        if name not in os.environ:
            return default
        v = os.environ.get(name, "").strip().lower()
        if not v:
            return default
        if v in ("1", "true", "yes", "on"):
            return True
        if v in ("0", "false", "no", "off"):
            return False
        return default

    def opt_int(name: str, default: int) -> int:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return default
        return int(raw)

    # --- Qué días puede enviar una corrida ---
    # Si no está definido, queda week. El .env de producción pone today (puesta al día hasta la fecha de corrida).
    parte_scope = opt("NODUM_PARTE_SCOPE", "week").strip().lower()
    if parte_scope not in ("today", "week", "backfill"):
        raise ValueError(
            f"Invalid NODUM_PARTE_SCOPE={parte_scope!r}; use 'today', 'week', or 'backfill'."
        )

    # --- Archivo de estado local ---
    # Solo un nombre de archivo, resuelto junto a main.py. Una ruta permitiría que un ambiente pise a otro.
    nodum_backfill_state_disabled = env_truthy("NODUM_BACKFILL_STATE_DISABLE")
    _state_file_raw = opt(
        "NODUM_BACKFILL_STATE_FILE", "maternity_leave_sync_state.json"
    ).strip()
    _sf = Path(_state_file_raw)
    if _sf.is_absolute() or len(_sf.parts) != 1:
        raise ValueError(
            f"NODUM_BACKFILL_STATE_FILE must be a filename only (no path), got {_state_file_raw!r}"
        )
    nodum_backfill_state_file = _sf.name

    # --- Mensajes de duplicado que no son fallo ---
    # Clave ausente: frases en español por defecto. Clave presente pero vacía: sin excepciones.
    dup_key = "NODUM_DUPLICATE_OK_SUBSTRINGS"
    dup_default_csv = "ya existe,duplicado,registro duplicado,parte ya existe"
    if dup_key not in os.environ:
        nodum_duplicate_ok_substrings = tuple(
            x.strip().lower() for x in dup_default_csv.split(",") if x.strip()
        )
    elif not os.environ.get(dup_key, "").strip():
        nodum_duplicate_ok_substrings = ()
    else:
        nodum_duplicate_ok_substrings = tuple(
            x.strip().lower()
            for x in os.environ.get(dup_key, "").split(",")
            if x.strip()
        )

    # --- Código de departamento de RRHH hacia el proyecto de Nodum ---
    # Se guarda en minúsculas. "A001=PRY00375, CDE=PRY00376". Los tramos sin "=" se ignoran.
    dept_map_key = "NODUM_MATERNITY_PROJECT_BY_DEPT"
    nodum_maternity_project_by_dept: dict[str, str] = {}
    if dept_map_key in os.environ:
        raw_map = os.environ.get(dept_map_key, "").strip()
        if raw_map:
            for segment in raw_map.split(","):
                segment = segment.strip()
                if not segment or "=" not in segment:
                    continue
                dept_code, _, proyecto = segment.partition("=")
                dept_code, proyecto = dept_code.strip(), proyecto.strip()
                if dept_code and proyecto:
                    nodum_maternity_project_by_dept[dept_code.casefold()] = proyecto

    # --- "Hoy" ficticio para una prueba ---
    # Solo fecha ISO. Las validaciones de producción lo rechazan si SYNC_PRODUCTION=1.
    test_date_key = "SYNC_TEST_DATE"
    sync_test_date: date | None = None
    if test_date_key in os.environ:
        raw_td = os.environ.get(test_date_key, "").strip()
        if raw_td:
            try:
                sync_test_date = date.fromisoformat(raw_td)
            except ValueError as e:
                raise ValueError(
                    f"Invalid {test_date_key}={raw_td!r}; use ISO YYYY-MM-DD"
                ) from e

    # --- Catálogo ERP para resolver el proyecto de maternidad ---
    # El nombre se interpola en el SQL, así que solo admite letras, dígitos y guión bajo.
    maternity_pry_use_cabidrecurso = opt_bool("MATERNITY_PRY_USE_CABIDRECURSO", True)
    amaral_catalog_database = opt("AMARAL_CATALOG_DATABASE", "amaral01").strip()
    if maternity_pry_use_cabidrecurso:
        if not amaral_catalog_database:
            raise ValueError(
                "AMARAL_CATALOG_DATABASE is required when MATERNITY_PRY_USE_CABIDRECURSO is enabled (default on)"
            )
        if not _CATALOG_DB_SAFE.match(amaral_catalog_database):
            raise ValueError(
                f"Invalid AMARAL_CATALOG_DATABASE={amaral_catalog_database!r}; "
                "use letters, digits, underscore only"
            )

    return Settings(
        sql_driver=req("SQL_SERVER_DRIVER"),
        sql_server=req("SQL_SERVER_SERVER"),
        sql_database=req("SQL_SERVER_DATABASE"),
        sql_uid=req("SQL_SERVER_UID"),
        sql_pwd=req("SQL_SERVER_PWD"),
        sql_encrypt=opt("SQL_ENCRYPT", ""),
        sql_trust_server_certificate=opt_bool(
            "SQL_TRUST_SERVER_CERTIFICATE", True
        ),
        sql_col_lic_fecha_inicio=opt("SQL_COL_LIC_FECHA_INICIO", "fecha_inicio"),
        sql_col_lic_fecha_fin=opt("SQL_COL_LIC_FECHA_FIN", "fecha_fin"),
        sql_col_trab_centro_costo=opt("SQL_COL_TRAB_CENTRO_COSTO", "centro_costo"),
        sql_col_tit_nombre=from_env_optional("SQL_COL_TIT_NOMBRE"),
        sql_col_tit_apellido=from_env_optional("SQL_COL_TIT_APELLIDO"),
        sql_col_trab_estado=opt("SQL_COL_TRAB_ESTADO", "estado_trab"),
        sql_trab_estado_activo=opt("SQL_TRAB_ESTADO_ACTIVO", "A"),
        sql_require_trabajador_activo=opt_bool("SQL_REQUIRE_TRABAJADOR_ACTIVO", False),
        nodum_wsdl=req("NODUM_WSDL_URL"),
        nodum_username=req("NODUM_USERNAME"),
        nodum_password=req("NODUM_PASSWORD"),
        nodum_read_username=from_env_optional("NODUM_READ_USERNAME"),
        nodum_read_password=from_env_optional("NODUM_READ_PASSWORD"),
        nodum_read_wsdl=opt("NODUM_READ_WSDL_URL", ""),
        nodum_read_operation=opt("NODUM_READ_OPERATION", ""),
        nodum_read_param_recurso=opt("NODUM_READ_PARAM_RECURSO", "CodigoIdentificacion"),
        nodum_read_param_fecha_desde=opt(
            "NODUM_READ_PARAM_FECHA_DESDE", "FechaDesde"
        ),
        nodum_read_param_fecha_hasta=opt(
            "NODUM_READ_PARAM_FECHA_HASTA", "FechaHasta"
        ),
        nodum_read_request_root=opt("NODUM_READ_REQUEST_ROOT", "RPryConsHorsxTit"),
        nodum_read_recurso_key=opt("NODUM_READ_RECURSO_KEY", "CodigoIdentificacion"),
        nodum_read_fecha_key=opt("NODUM_READ_FECHA_KEY", "FechaDocumento"),
        nodum_read_horas_key=opt("NODUM_READ_HORAS_KEY", "Horasdeduracion"),
        nodum_read_codigo_actividad_key=opt(
            "NODUM_READ_CODIGO_ACTIVIDAD_KEY", "CodigodeActividad"
        ),
        nodum_read_centro_costo_key=opt(
            "NODUM_READ_CENTRO_COSTO_KEY", "CentrodeCosto"
        ),
        nodum_read_filter_codigo_actividad=opt(
            "NODUM_READ_FILTER_CODIGO_ACTIVIDAD", ""
        ),
        nodum_read_filter_centro_costo=opt("NODUM_READ_FILTER_CENTRO_COSTO", ""),
        nodum_read_match_resolved_proyecto=opt_bool(
            "NODUM_READ_MATCH_RESOLVED_PROYECTO", True
        ),
        nodum_read_line_substring_fallback=(
            "maternidad"
            if "NODUM_READ_LINE_SUBSTRING_FALLBACK" not in os.environ
            else os.environ.get("NODUM_READ_LINE_SUBSTRING_FALLBACK", "").strip()
        ),
        nodum_fecha_documento_strftime=fmt,
        nodum_codigo_empresa=opt("NODUM_CODIGO_EMPRESA", "01"),
        nodum_g1_observaciones=opt("NODUM_G1_OBSERVACIONES", "licencia maternidad automatic"),
        nodum_g2_codigo_actividad=opt("NODUM_G2_CODIGO_ACTIVIDAD", "001"),
        nodum_g2_horas=opt_float("NODUM_G2_HORAS", 8.0),
        nodum_parte_scope=parte_scope,
        nodum_dry_run=opt_bool("NODUM_DRY_RUN", True),
        nodum_soap_connect_timeout=opt_int("NODUM_SOAP_CONNECT_TIMEOUT", 30),
        nodum_soap_read_timeout=opt_int("NODUM_SOAP_READ_TIMEOUT", 30),
        nodum_duplicate_ok_substrings=nodum_duplicate_ok_substrings,
        nodum_maternity_project_by_dept=nodum_maternity_project_by_dept,
        nodum_g2_centrode_costo=from_env_str("NODUM_G2_CENTRODECOSTO", "PRY00380"),
        nodum_g2_observaciones_1=from_env_optional("NODUM_G2_OBSERVACIONES_1"),
        sql_col_feriado_fecha=opt("SQL_COL_FERIADO_FECHA", "fecha"),
        sync_force_run=env_truthy("SYNC_FORCE_RUN"),
        sync_test_date=sync_test_date,
        amaral_catalog_database=amaral_catalog_database,
        maternity_pry_use_cabidrecurso=maternity_pry_use_cabidrecurso,
        nodum_backfill_state_disabled=nodum_backfill_state_disabled,
        nodum_backfill_state_file=nodum_backfill_state_file,
    )
