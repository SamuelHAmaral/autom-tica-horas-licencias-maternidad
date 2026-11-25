# Mantenimiento del sincronizador

Esta guía es para quien va a cambiar el código. La operación del servidor está en [README.md](../README.md) y en [PRODUCTION.md](PRODUCTION.md).

El job no tiene pantallas. Una corrida lee licencias `maternal` en SQL Server, arma un parte diario por cada día hábil que todavía no llega a `NODUM_G2_HORAS` (8) y lo envía a Nodum con `procesarAlta`.

## Recorrido de una corrida

1. `main.py` lee `.env` y arma `Settings`.
2. Con `SYNC_PRODUCTION=1`, `src/production_checks.py` corta la corrida si `NODUM_DRY_RUN` está encendido o si hay `SYNC_TEST_DATE`.
3. `src/calendar_gate.py` no corre sábado, domingo ni un día que esté en `ct_RHFeriados`, salvo `SYNC_FORCE_RUN=1`.
4. `src/extractor.py` trae las licencias activas (`cod_tipo_licen = 'maternal'`).
5. El mismo módulo carga los feriados del rango que pide el alcance (`today` / `week` / `backfill`).
6. `src/transformer.py` deja solo días hábiles dentro de la licencia.
7. Con alcance `today` o `backfill` y **sin** lectura Nodum, `src/backfill_state.py` recorta los días anteriores a `last_ok_fecha`. Con lectura Nodum encendida esa marca de agua no recorta: hay que mirar el hueco real.
8. `src/loader.py` consulta las horas ya cargadas y se queda con las líneas del proyecto maternidad.
9. `src/hours_gap.py` calcula lo que falta hasta 8 h. Un día completo no se envía.
10. `src/transformer.py` arma los datos de un parte `TpryParteDiaGS` por día.
11. `src/loader.py` llama `procesarAlta` (o solo lo registra si `NODUM_DRY_RUN=1`).
12. Si Nodum acepta, se actualiza `maternity_leave_sync_state.json`.

Códigos de salida: 0 corrida sana o sin trabajo, 1 configuración, 2 SQL, 3 Nodum.

## Dónde cambiar cada cosa

| Si hay que cambiar… | Ir a… |
|---------------------|--------|
| El tipo de licencia o los JOIN de RRHH | `src/extractor.py` (`build_active_maternity_leaves_sql`) |
| Nombres físicos de columnas | `.env` (`SQL_COL_*`). El SQL solo acepta identificadores simples |
| Qué días entran en la corrida | `NODUM_PARTE_SCOPE` y las funciones `leave_working_dates_*` de `src/transformer.py` |
| El proyecto Nodum (`G2.CentrodeCosto`) | `resolve_g2_centrode_costo` en `src/transformer.py`. El orden es: proyecto ERP `ct_cabidrecursos` (nombre con `maternidad`), después `NODUM_MATERNITY_PROJECT_BY_DEPT`, después `NODUM_G2_CENTRODECOSTO` |
| Horas, actividad, empresa, texto del parte | `.env` (`NODUM_G2_*`, `NODUM_CODIGO_EMPRESA`, `NODUM_G1_OBSERVACIONES`) |
| Cuándo un día ya está completo | `src/hours_gap.py` |
| Qué líneas de la lectura Nodum cuentan como maternidad | `_read_line_matches_maternity_proyecto` en `src/loader.py` |
| Un mensaje de Nodum que en realidad es “ya existía” | `NODUM_DUPLICATE_OK_SUBSTRINGS` |
| No correr feriados o fines de semana | `src/calendar_gate.py` y la tabla `ct_RHFeriados` |
| Qué se considera inseguro en producción | `src/production_checks.py` |
| Credenciales y URLs | `.env` (no se commitea; plantilla en `.env.example`) |

Los scripts de `scripts/` solo consultan catálogos (departamento RRHH, negocio ERP, proyecto PRY). Sirven para armar `NODUM_MATERNITY_PROJECT_BY_DEPT`. No cargan partes.

`run_daily_sync.sh` entra al proyecto y usa `.venv/bin/python`. Las dependencias se instalan en ese virtualenv, no en el Python del sistema.

## Reglas que conviene no romper

- **Una llamada SOAP por día y por persona.** El parte lleva una sola línea `G2`, no varios días juntos.
- **Las horas ya cargadas son el máximo entre el archivo de estado local y Nodum.** Si uno de los dos dice 8 h, no se reenvía. Si Nodum dice 2 h y el archivo dice 8 h, tampoco.
- **La marca `last_ok_fecha` solo recorta fechas cuando la lectura Nodum está apagada.** Con `NODUM_READ_OPERATION=simular`, un día fallido en el medio se vuelve a intentar aunque un día posterior haya salido bien.
- **La marca pertenece a una licencia.** Si cambia `fec_inicio`, es otra licencia y no se reutiliza la marca de agua.
- **Dos filas SQL del mismo `recurso_id` en la misma corrida:** se procesa la primera y se salta el resto, para no cargar dos veces.
- **`NODUM_BACKFILL_STATE_FILE` es solo un nombre de archivo**, junto a `main.py`. No acepta rutas.
- **`NODUM_DRY_RUN` por defecto queda encendido** si la variable no está en el entorno. En el servidor tiene que estar en `0`, y `SYNC_PRODUCTION=1` impide arrancar si sigue en `1`.
- **No copiar `maternity_leave_sync_state.json` de un ambiente a otro.** El job creería que esos días ya se enviaron.

## Probar un cambio

Los tests no abren SQL ni Nodum. Correrlos con el virtualenv del proyecto, desde la raíz:

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

Cubren días hábiles, proyecto G2, forma del parte, hueco de horas, archivo de estado local, lectura de `.env`, el filtro de la lectura Nodum, el SQL que se arma y el corte de fin de semana.

Para ver el efecto contra datos reales sin grabar en Nodum:

1. En `.env`, dejar `SYNC_PRODUCTION` apagado (`0` o sin definir). Con `SYNC_PRODUCTION=1` el job no arranca si `NODUM_DRY_RUN=1`.
2. Poner `NODUM_DRY_RUN=1`.
3. Correr `python3 scripts/audit_maternity_sql.py` y después `.venv/bin/python main.py`.
4. Revisar `maternity_leave_sync.log`. Con `NODUM_DRY_RUN=1` no se llama a `procesarAlta` y no se actualiza el archivo de estado.

`SYNC_TEST_DATE=YYYY-MM-DD` simula “hoy” para el calendario, la semana ISO y el filtro de licencias. Hay que sacarla antes de volver a producción.

Al agregar una regla, conviene un test en `tests/` que falle con el comportamiento viejo y pase con el nuevo. Los módulos de fechas, archivo de estado, configuración y SQL armado se pueden probar sin red. `main.py` sigue siendo el lugar que une esos pasos; la decisión de “cuántas horas faltan” está en `src/hours_gap.py` para no tener que leer todo el bucle.
