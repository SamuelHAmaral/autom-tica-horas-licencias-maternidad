"""Arma un Settings para las pruebas.

Nota: los defaults se parecen a una configuración de Amaral01. Pasar solo el
campo que la prueba quiere cambiar. No usa el entorno ni la red.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.settings import Settings


def sample_settings(**overrides: Any) -> Settings:
    data: dict[str, Any] = {
        "sql_driver": "{ODBC Driver 17 for SQL Server}",
        "sql_server": "sql.example",
        "sql_database": "RRHHAmaral",
        "sql_uid": "user",
        "sql_pwd": "secret",
        "sql_encrypt": "",
        "sql_trust_server_certificate": True,
        "sql_col_lic_fecha_inicio": "fec_inicio",
        "sql_col_lic_fecha_fin": "fec_final",
        "sql_col_trab_centro_costo": "cod_dpto",
        "sql_col_tit_nombre": "nom_tit",
        "sql_col_tit_apellido": "",
        "sql_col_trab_estado": "estado_trab",
        "sql_trab_estado_activo": "A",
        "sql_require_trabajador_activo": False,
        "nodum_wsdl": "http://nodum.example:8080/soap/Amaral01/services/forms/v1.3/TpryParteDiaGS?wsdl",
        "nodum_username": "nodum",
        "nodum_password": "secret",
        "nodum_read_username": "",
        "nodum_read_password": "",
        "nodum_read_wsdl": "",
        "nodum_read_operation": "simular",
        "nodum_read_param_recurso": "CodigoTitular",
        "nodum_read_param_fecha_desde": "Dia",
        "nodum_read_param_fecha_hasta": "FechaAuxiliar",
        "nodum_read_request_root": "RPryConsHorsxTit",
        "nodum_read_recurso_key": "R_CodigoTitular",
        "nodum_read_fecha_key": "R_FechaDocumento",
        "nodum_read_horas_key": "R_Cant.Horas",
        "nodum_read_codigo_actividad_key": "R_NombredeActividad",
        "nodum_read_centro_costo_key": "R_NombreCentrodeCostos",
        "nodum_read_filter_codigo_actividad": "",
        "nodum_read_filter_centro_costo": "",
        "nodum_read_match_resolved_proyecto": True,
        "nodum_read_line_substring_fallback": "maternidad",
        "nodum_fecha_documento_strftime": "%Y-%m-%d",
        "nodum_codigo_empresa": "01",
        "nodum_g1_observaciones": "licencia maternidad automatic",
        "nodum_g2_codigo_actividad": "001",
        "nodum_g2_horas": 8.0,
        "nodum_parte_scope": "today",
        "nodum_dry_run": False,
        "nodum_soap_connect_timeout": 30,
        "nodum_soap_read_timeout": 30,
        "nodum_duplicate_ok_substrings": ("ya existe", "duplicado"),
        "nodum_g2_centrode_costo": "PRY00380",
        "nodum_maternity_project_by_dept": {"a001": "PRY00375"},
        "nodum_g2_observaciones_1": "",
        "sql_col_feriado_fecha": "fecha",
        "sync_force_run": False,
        "sync_test_date": None,
        "amaral_catalog_database": "amaral01",
        "maternity_pry_use_cabidrecurso": True,
        "nodum_backfill_state_disabled": False,
        "nodum_backfill_state_file": "maternity_leave_sync_state.json",
    }
    data.update(overrides)
    if "sync_test_date" in overrides and isinstance(overrides["sync_test_date"], str):
        data["sync_test_date"] = date.fromisoformat(overrides["sync_test_date"])
    return Settings(**data)
