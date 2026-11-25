# Sincronización de horas por licencia de maternidad (RRHH → Nodum)

Job en Python que lee las **licencias de maternidad activas** en SQL Server (`RRHHAmaral`) y envía las **horas por día hábil** a **Nodum** por SOAP (`procesarAlta` / `TpryParteDiaGS`).

Nota: operación del servidor en esta página y en [docs/PRODUCTION.md](docs/PRODUCTION.md). Para cambiar el código, [docs/MANTENIMIENTO.md](docs/MANTENIMIENTO.md).

## Requisitos

- Python 3.10+
- Controlador ODBC para SQL Server (p. ej. 17)
- Acceso de red a SQL Server y a Nodum

```bash
pip install -r requirements.txt
```

## Configuración

1. Copiar `.env.example` a `.env` y completar credenciales y URLs (no subir `.env` al repositorio).
2. **`NODUM_PARTE_SCOPE`** define qué días se envían por corrida:

   | Valor | Comportamiento |
   |--------|----------------|
   | **`today`** | Todos los días hábiles de la licencia desde **`fec_inicio`** hasta el día de corrida. Omite los que ya están completos en Nodum (lectura) y/o en el archivo de estado local. **Recomendado** con tarea diaria: si el cron falla varios días, la siguiente corrida recupera los faltantes. |
   | **`week`** | Todos los días hábiles de la **semana ISO actual** que caen dentro de `[fec_inicio, fec_final]`. |
   | **`backfill`** | Mismo rango que **`today`** (alias de puesta al día). |

3. **State y duplicados:** por defecto se usa **`maternity_leave_sync_state.json`** (junto a `main.py`) para recordar horas ya enviadas. Con **`NODUM_READ_OPERATION`** activo (recomendado), cada corrida consulta Nodum sobre toda la ventana de licencia y solo envía la diferencia hasta `NODUM_G2_HORAS` (8), así no quedan huecos tras una caída. La marca de agua `last_ok_fecha` solo acota fechas cuando la lectura Nodum está apagada. **`NODUM_BACKFILL_STATE_DISABLE=1`** desactiva el archivo. **`NODUM_BACKFILL_STATE_FILE`** solo admite un nombre de archivo (sin rutas).

4. **Lectura previa desde Nodum (recomendado en producción):** con `NODUM_READ_OPERATION=simular`, el job consulta Amaral01 antes de cargar, cuenta solo líneas del **proyecto maternidad** resuelto (`NODUM_READ_MATCH_RESOLVED_PROYECTO=1`) y envía solo la diferencia hasta `NODUM_G2_HORAS` (8).

5. Mapear `cod_dpto` de RRHH a proyectos Nodum con **`NODUM_MATERNITY_PROJECT_BY_DEPT`**; con **`MATERNITY_PRY_USE_CABIDRECURSO=1`** (por defecto) se prioriza el proyecto maternidad del ERP (`amaral01` / `ct_cabidrecursos`). Los scripts en `scripts/` ayudan a mantener mapeos.

## Producción

Guía paso a paso: **[docs/PRODUCTION.md](docs/PRODUCTION.md)**.

Resumen:

| Variable | Producción |
|----------|------------|
| `SYNC_PRODUCTION` | `1` |
| `NODUM_DRY_RUN` | `0` |
| `NODUM_PARTE_SCOPE` | `today` (tarea diaria; la corrida siguiente completa los días que faltaron) |
| `NODUM_WSDL_URL` / `NODUM_READ_WSDL_URL` | Ruta `/soap/Amaral01/...` |
| `SYNC_TEST_DATE` | no definir |

Programación Linux (cron):

1. Dar permisos al lanzador: `chmod +x run_daily_sync.sh`
2. Editar cron: `crontab -e`
3. Programar (ejemplo lunes a viernes 06:15):

```cron
15 6 * * 1-5 /var/www/licencia-maternidad/run_daily_sync.sh >> /var/www/licencia-maternidad/cron.log 2>&1
```

Con `SYNC_PRODUCTION=1`, el job **no arranca** si `NODUM_DRY_RUN=1` o si `SYNC_TEST_DATE` está definido.

## Ejecución

```bash
python3 main.py
```

- **`NODUM_DRY_RUN=1`**: arma el payload y registra en log; **no** llama a Nodum y **no** actualiza el archivo de estado de backfill.
- Log rotativo: **`maternity_leave_sync.log`**.

### Variables para lectura previa Nodum

Estas variables permiten adaptar la consulta al WSDL de lectura:

- `NODUM_READ_WSDL_URL` (opcional): WSDL de consulta. Si se omite, usa `NODUM_WSDL_URL`.
- `NODUM_READ_OPERATION`: nombre de operación SOAP de lectura (si está vacío, la lectura queda apagada).
- `NODUM_READ_PARAM_RECURSO`, `NODUM_READ_PARAM_FECHA_DESDE`, `NODUM_READ_PARAM_FECHA_HASTA`: nombres de parámetros de entrada del método SOAP.
- `NODUM_READ_RECURSO_KEY`, `NODUM_READ_FECHA_KEY`, `NODUM_READ_HORAS_KEY`: claves esperadas en la respuesta para parsear recurso/fecha/horas.
- `NODUM_READ_CODIGO_ACTIVIDAD_KEY`, `NODUM_READ_CENTRO_COSTO_KEY`: claves para filtros opcionales.
- `NODUM_READ_FILTER_CODIGO_ACTIVIDAD`, `NODUM_READ_FILTER_CENTRO_COSTO`: filtros fijos opcionales (vacío = usar match por proyecto resuelto).
- `NODUM_READ_MATCH_RESOLVED_PROYECTO`, `NODUM_READ_LINE_SUBSTRING_FALLBACK`: evitan contar horas de otros proyectos como “maternidad completa”.
- `NODUM_CODIGO_EMPRESA`: empresa en G1 (por defecto `01`).

La corrida **no** se ejecuta en fin de semana ni si el día actual está en **`ct_RHFeriados`**, salvo **`SYNC_FORCE_RUN=1`**.

### Probar con otra fecha (sin cambiar el reloj del servidor)

**`SYNC_TEST_DATE=YYYY-MM-DD`** en `.env`: esa fecha actúa como “hoy” para el calendario, la semana ISO, el filtro SQL de licencias activas y el tope del **backfill**. Aparece un **WARNING** en el log; **quitar en producción**. Si la fecha cae en sábado/domingo o feriado y querés forzar la corrida, usar **`SYNC_FORCE_RUN=1`**.

### Códigos de salida (scheduler / cron)

| Código | Significado |
|--------|-------------|
| 0 | Éxito, omitido (fin de semana / feriado) o nada que procesar |
| 1 | Error de configuración / `.env` |
| 2 | Falló la extracción SQL o la consulta de feriados |
| 3 | Nodum rechazó la carga o error SOAP |

Solo **`estado == 0`** cuenta como éxito estricto; **`NODUM_DUPLICATE_OK_SUBSTRINGS`** permite tratar ciertos mensajes de duplicado como no fallo (y en backfill, avanzan la marca de agua si aplica).

## Scripts de ayuda (`scripts/`)

| Script | Uso |
|--------|-----|
| `list_cod_dpto.py` | Valores distintos de `cod_dpto` en RRHH |
| `list_hr_dpto_to_negocio.py` | RRHH `cod_dpto` → ERP `cod_negocio` (`amaral01`) |
| `list_maternity_negocio_to_pry.py` | ERP `cod_negocio` → proyecto maternidad **PRY** |
| `list_maternity_dpto_catalog.py` | Catálogo detallado (muchas filas) |
| `find_maternity_multi_dept_day.py` | Días hábiles con 2+ recursos y 2+ `cod_dpto` en maternidad |
| `audit_maternity_sql.py` | Licencias maternal “hoy” (misma consulta que el sync) + **CentrodeCosto** resuelto |

Opcional: **`AMARAL_CATALOG_DATABASE`** si la base ERP no es `amaral01`.

## Para quien mantiene el código

Guía de recorrido, reglas y “dónde cambiar cada cosa”: **[docs/MANTENIMIENTO.md](docs/MANTENIMIENTO.md)**.

Los tests no abren SQL ni Nodum. Correrlos con el virtualenv del proyecto:

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

## Estructura del proyecto

- `main.py` — punto de entrada  
- `src/extractor.py` — SQL Server (`pyodbc`)  
- `src/transformer.py` — fechas hábiles, datos del parte, resolución G2  
- `src/hours_gap.py` — horas que todavía faltan en cada día hábil  
- `src/loader.py` — SOAP (`zeep`)  
- `src/settings.py` — variables de entorno  
- `src/calendar_gate.py` — fin de semana / feriados  
- `src/backfill_state.py` — JSON de marca de agua para `backfill`  
- `src/logging_config.py` — consola + log rotativo  
- `src/production_checks.py` — validaciones pre-producción (`SYNC_PRODUCTION`)  
- `tests/` — reglas de negocio sin red  
- `run_daily_sync.sh` — entrada para `cron` en Linux  
- `run_daily_sync.bat` — alternativa para el Programador de tareas de Windows  
- `docs/PRODUCTION.md` — lista de despliegue  
- `docs/MANTENIMIENTO.md` — guía para cambiar el código  
