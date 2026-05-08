# Sincronización de horas por licencia de maternidad (RRHH → Nodum)

Job en Python que lee las **licencias de maternidad activas** en SQL Server (`RRHHAmaral`) y envía las **horas por día hábil** a **Nodum** por SOAP (`procesarAlta` / `TpryParteDiaGS`).

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
   | **`today`** | Solo el día de corrida (si está en licencia, es lun–vie y no es feriado en `ct_RHFeriados`). Recomendado con tarea diaria. |
   | **`week`** | Todos los días hábiles de la **semana ISO actual** que caen dentro de `[fec_inicio, fec_final]`. |
   | **`backfill`** | Todos los días hábiles desde **`fec_inicio`** hasta **`min(fec_final, día de corrida)`**. Sirve cuando la licencia se carga tarde en RRHH: el inicio real debe estar bien cargado en SQL; el job no usa la fecha de alta del registro. |

3. **Backfill y duplicados:** con `backfill`, por defecto se usa **`maternity_leave_sync_state.json`** (junto a `main.py`) como *marca de agua* por `recurso_id` + `fec_inicio`: solo se envían fechas **posteriores** al último día ya aceptado o marcado como duplicado aceptable en Nodum. Así se puede dejar `backfill` activo sin reenviar toda la historia cada día. **`NODUM_BACKFILL_STATE_DISABLE=1`** desactiva el archivo y vuelve al comportamiento de reintentar todo el rango (útil si confías solo en mensajes de duplicado). **`NODUM_BACKFILL_STATE_FILE`** solo admite un nombre de archivo (sin rutas).

4. **Lectura previa desde Nodum (opcional):** si configurás `NODUM_READ_OPERATION`, el job consulta Nodum antes de cargar, suma horas ya existentes por `recurso + fecha` y envía solo la diferencia hasta `NODUM_G2_HORAS` (por defecto 8). Sin esa config, usa el estado local JSON como referencia.

4. Mapear `cod_dpto` de RRHH a proyectos Nodum con **`NODUM_MATERNITY_PROJECT_BY_DEPT`**; con **`MATERNITY_PRY_USE_CABIDRECURSO=1`** (por defecto) se prioriza el proyecto maternidad del ERP (`amaral01` / `ct_cabidrecursos`). Los scripts en `scripts/` ayudan a mantener mapeos.

## Ejecución

```bash
py -3 main.py
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
- `NODUM_READ_FILTER_CODIGO_ACTIVIDAD`, `NODUM_READ_FILTER_CENTRO_COSTO`: si se definen, solo se computan líneas que coincidan.

La corrida **no** se ejecuta en fin de semana ni si el día actual está en **`ct_RHFeriados`**, salvo **`SYNC_FORCE_RUN=1`**.

### Probar con otra fecha (sin cambiar el reloj del servidor)

**`SYNC_TEST_DATE=YYYY-MM-DD`** en `.env`: esa fecha actúa como “hoy” para el calendario, la semana ISO, el filtro SQL de licencias activas y el tope del **backfill**. Aparece un **WARNING** en el log; **quitar en producción**. Si la fecha cae en sábado/domingo o feriado y querés forzar la corrida, usar **`SYNC_FORCE_RUN=1`**.

### Códigos de salida (programador de tareas)

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

## Estructura del proyecto

- `main.py` — punto de entrada  
- `src/extractor.py` — SQL Server (`pyodbc`)  
- `src/transformer.py` — fechas hábiles, payloads, resolución G2  
- `src/loader.py` — SOAP (`zeep`)  
- `src/settings.py` — variables de entorno  
- `src/calendar_gate.py` — fin de semana / feriados  
- `src/backfill_state.py` — JSON de marca de agua para `backfill`  
- `src/logging_config.py` — consola + log rotativo  
