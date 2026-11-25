# Checklist de despliegue en producción

Usar esto antes de programar el job en el servidor de producción.

Nota: esta página es para el servidor. Los cambios de código y las reglas de negocio están en [MANTENIMIENTO.md](MANTENIMIENTO.md).

## 1. Archivo de entorno (`.env`)

Copiar `.env.example` a `.env` en el servidor. **Nunca commitear `.env`.**

| Variable | Valor en producción |
|----------|---------------------|
| `SYNC_PRODUCTION` | `1` (impide dry-run y fecha de prueba) |
| `NODUM_DRY_RUN` | `0` |
| `NODUM_PARTE_SCOPE` | `today` (tarea diaria; la corrida siguiente completa los días de licencia que faltaron hasta la fecha de corrida) |
| `NODUM_WSDL_URL` | `http://<host>:8080/soap/Amaral01/services/forms/v1.3/TpryParteDiaGS?wsdl` |
| `NODUM_READ_WSDL_URL` | `http://<host>:8080/soap/Amaral01/services/sim/v1.3/RPryConsHorsxTit?wsdl` |
| `NODUM_READ_OPERATION` | `simular` |
| `NODUM_READ_MATCH_RESOLVED_PROYECTO` | `1` |
| `AMARAL_CATALOG_DATABASE` | `amaral01` |
| `SYNC_TEST_DATE` | **sin definir** |
| `SYNC_FORCE_RUN` | **sin definir** (salvo una corrida manual en feriado) |

Confirmar que SQL apunta al RRHH de producción (`SQL_SERVER_*`) y que las credenciales de Nodum tienen acceso a los servicios forms y sim de **Amaral01**.

## 2. Puesta al día diaria y backfill

1. **Tarea diaria de producción:** dejar `NODUM_PARTE_SCOPE=today`. Cada corrida recorre los días hábiles de la licencia desde `fec_inicio` hasta hoy, pregunta a Nodum qué ya está cargado y envía solo las horas que faltan. Después de varios días caído, la siguiente corrida que salga bien completa los huecos.
2. **`backfill`:** mismo rango de fechas que `today` (queda como alias). Para la tarea programada conviene `today`.
3. Dejar `maternity_leave_sync_state.json` en el servidor (está en `.gitignore`) y dejar `NODUM_READ_OPERATION=simular` activo, así lo que ya está completo se mira en Nodum y no solo en el archivo local.

## 3. Prueba previa en el servidor (Linux)

```bash
cd /var/www/licencia-maternidad
python3 scripts/audit_maternity_sql.py
python3 main.py
```

- Código de salida **0** = éxito o nada que hacer (fin de semana, feriado o ya sincronizado).
- Código de salida **3** = Nodum rechazó una carga; revisar `maternity_leave_sync.log`.
- El script de auditoría lista quién está en licencia maternal activa y el `G2.CentrodeCosto` resuelto.

## 4. Cron (programador de Linux)

1. El lanzador tiene que poder ejecutarse: `chmod +x /var/www/licencia-maternidad/run_daily_sync.sh`.
2. Editar el crontab de la cuenta que corre el job: `crontab -e`.
3. Agregar el horario de días hábiles (ejemplo 06:15):

```cron
15 6 * * 1-5 /var/www/licencia-maternidad/run_daily_sync.sh >> /var/www/licencia-maternidad/cron.log 2>&1
```

4. Usar una cuenta de servicio con acceso de red a SQL y a Nodum.
5. Validar con `crontab -l` y seguir `cron.log` y `maternity_leave_sync.log`.

## 5. Monitoreo

- Log: `maternity_leave_sync.log` (rota a los 10 MB, 5 copias).
- Buscar `CRITICAL`, `estado=0`, `Grabado Correctamente`, `Production check`.
- Archivo de estado: `maternity_leave_sync_state.json` (marca de agua por recurso).

## 6. Seguridad

- Limitar el acceso al archivo `.env` a la cuenta que corre el job.
- No copiar un `maternity_leave_sync_state.json` de prueba a producción salvo que sea a propósito.

## Códigos de salida (cron / programador)

| Código | Significado |
|--------|-------------|
| 0 | OK u omitido (sin trabajo) |
| 1 | Falló la configuración o las validaciones de producción |
| 2 | Error de SQL |
| 3 | Falló la carga en Nodum |
