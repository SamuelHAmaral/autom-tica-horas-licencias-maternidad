"""Estado JSON local: horas ya enviadas y una marca de agua por licencia.

Nota: main aplica la marca de agua solo cuando la lectura de Nodum está apagada.
El archivo vive junto a main.py y no hay que copiarlo entre ambientes.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Mapping

STATE_VERSION = 1


def _recurso_key(recurso_id: object) -> str:
    """Clave del archivo de estado. Recorta espacios para que '100' y '100 ' sean el mismo titular."""
    return str(recurso_id).strip()


def load(path: Path) -> dict[str, Any]:
    """Lee el estado JSON. Si el archivo falta o está corrupto, arranca vacío para que la corrida siga."""
    if not path.is_file():
        return {"version": STATE_VERSION, "by_recurso": {}}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {"version": STATE_VERSION, "by_recurso": {}}
    if not isinstance(data, dict):
        return {"version": STATE_VERSION, "by_recurso": {}}
    data.setdefault("version", STATE_VERSION)
    data.setdefault("by_recurso", {})
    if not isinstance(data["by_recurso"], dict):
        data["by_recurso"] = {}
    return data


def save(path: Path, data: dict[str, Any]) -> None:
    """Reemplaza el archivo vía un nombre temporal para que un corte a mitad no deje un JSON a medias."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def get_last_ok_fecha(
    data: Mapping[str, Any],
    recurso_id: object,
    fec_inicio: date,
) -> date | None:
    """Último día registrado como correcto para esta licencia, o None si no se conoce o es otra licencia."""
    key = _recurso_key(recurso_id)
    br = data.get("by_recurso") or {}
    if not isinstance(br, dict):
        return None
    entry = br.get(key)
    if not isinstance(entry, dict):
        return None
    try:
        stored_fi = date.fromisoformat(str(entry.get("fec_inicio", "")))
    except ValueError:
        return None
    if stored_fi != fec_inicio:
        return None
    raw_last = entry.get("last_ok_fecha")
    if not raw_last:
        return None
    try:
        return date.fromisoformat(str(raw_last))
    except ValueError:
        return None


def dates_after_watermark(dates: list[date], last_ok: date | None) -> list[date]:
    """Días estrictamente posteriores a last_ok. None significa que esta licencia todavía no tiene marca."""
    if last_ok is None:
        return list(dates)
    return [d for d in dates if d > last_ok]


def record_day_ok(
    data: dict[str, Any],
    recurso_id: object,
    fec_inicio: date,
    dia: date,
) -> None:
    """Avanza last_ok_fecha. Otro fec_inicio es otra licencia y reemplaza el episodio anterior."""
    key = _recurso_key(recurso_id)
    br = data.setdefault("by_recurso", {})
    if not isinstance(br, dict):
        data["by_recurso"] = {}
        br = data["by_recurso"]
    cur = br.get(key)
    if not isinstance(cur, dict) or cur.get("fec_inicio") != fec_inicio.isoformat():
        br[key] = {"fec_inicio": fec_inicio.isoformat(), "last_ok_fecha": dia.isoformat()}
        return
    prev_raw = cur.get("last_ok_fecha")
    try:
        prev = date.fromisoformat(str(prev_raw)) if prev_raw else None
    except ValueError:
        prev = None
    if prev is None or dia > prev:
        cur["last_ok_fecha"] = dia.isoformat()


def get_recorded_hours(
    data: Mapping[str, Any], recurso_id: object, dia: date
) -> float:
    """Horas ya anotadas en el estado local para ese recurso y ese día. Si el dato no sirve, devuelve 0."""
    hrs_root = data.get("hours_by_recurso_date") or {}
    if not isinstance(hrs_root, dict):
        return 0.0
    rec_entry = hrs_root.get(_recurso_key(recurso_id))
    if not isinstance(rec_entry, dict):
        return 0.0
    raw = rec_entry.get(dia.isoformat())
    if raw is None:
        return 0.0
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return v if v > 0 else 0.0


def record_hours(
    data: dict[str, Any], recurso_id: object, dia: date, add_hours: float
) -> None:
    """Suma al estado local las horas que se cargaron bien para ese recurso y ese día."""
    if add_hours <= 0:
        return
    hrs_root = data.setdefault("hours_by_recurso_date", {})
    if not isinstance(hrs_root, dict):
        data["hours_by_recurso_date"] = {}
        hrs_root = data["hours_by_recurso_date"]
    key = _recurso_key(recurso_id)
    rec_entry = hrs_root.setdefault(key, {})
    if not isinstance(rec_entry, dict):
        hrs_root[key] = {}
        rec_entry = hrs_root[key]
    dkey = dia.isoformat()
    prev = 0.0
    raw_prev = rec_entry.get(dkey)
    if raw_prev is not None:
        try:
            prev = float(raw_prev)
        except (TypeError, ValueError):
            prev = 0.0
    rec_entry[dkey] = max(0.0, prev + add_hours)


def mark_day_full(
    data: dict[str, Any], recurso_id: object, dia: date, target_hours: float
) -> None:
    """Marca el estado local como completo para ese recurso y ese día."""
    hrs_root = data.setdefault("hours_by_recurso_date", {})
    if not isinstance(hrs_root, dict):
        data["hours_by_recurso_date"] = {}
        hrs_root = data["hours_by_recurso_date"]
    key = _recurso_key(recurso_id)
    rec_entry = hrs_root.setdefault(key, {})
    if not isinstance(rec_entry, dict):
        hrs_root[key] = {}
        rec_entry = hrs_root[key]
    rec_entry[dia.isoformat()] = max(0.0, float(target_hours))
