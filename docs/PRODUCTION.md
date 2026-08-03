# Production deployment checklist

Use this before scheduling the job on the production server.

## 1. Environment file (`.env`)

Copy `.env.example` to `.env` on the server. **Never commit `.env`.**

| Setting | Production value |
|---------|----------------|
| `SYNC_PRODUCTION` | `1` (blocks dry-run / test date) |
| `NODUM_DRY_RUN` | `0` |
| `NODUM_PARTE_SCOPE` | `today` (daily job; auto catch-up of any missing leave days through run date) |
| `NODUM_WSDL_URL` | `http://<host>:8080/soap/Amaral01/services/forms/v1.3/TpryParteDiaGS?wsdl` |
| `NODUM_READ_WSDL_URL` | `http://<host>:8080/soap/Amaral01/services/sim/v1.3/RPryConsHorsxTit?wsdl` |
| `NODUM_READ_OPERATION` | `simular` |
| `NODUM_READ_MATCH_RESOLVED_PROYECTO` | `1` |
| `AMARAL_CATALOG_DATABASE` | `amaral01` |
| `SYNC_TEST_DATE` | **unset** |
| `SYNC_FORCE_RUN` | **unset** (unless manual run on holiday) |

Confirm SQL points at production RRHH (`SQL_SERVER_*`) and Nodum credentials have access to **Amaral01** forms + sim services.

## 2. Daily catch-up vs one-time backfill

1. **Production daily**: keep `NODUM_PARTE_SCOPE=today`. Each run scans working leave days from `fec_inicio` through today, asks Nodum what is already loaded, and submits only the missing hours. After a multi-day outage the next successful run fills the gaps.
2. **`backfill`**: same date range as `today` (kept as an alias). Prefer `today` for the scheduled job.
3. Keep `maternity_leave_sync_state.json` on the server (gitignored) and keep `NODUM_READ_OPERATION=simular` enabled so completeness is checked against Nodum, not only local state.

## 3. Pre-flight test on the server (Linux)

```bash
cd /var/www/licencia-maternidad
python3 scripts/audit_maternity_sql.py
python3 main.py
```

- Exit code **0** = success or nothing to do (weekend/holiday/already synced).
- Exit code **3** = Nodum rejected a load; check `maternity_leave_sync.log`.
- Audit script lists who is in active maternal leave and resolved `G2.CentrodeCosto`.

## 4. Cron (Linux scheduler)

1. Ensure launcher is executable: `chmod +x /var/www/licencia-maternidad/run_daily_sync.sh`.
2. Edit crontab for the run account: `crontab -e`.
3. Add weekday schedule (example 06:15):

```cron
15 6 * * 1-5 /var/www/licencia-maternidad/run_daily_sync.sh >> /var/www/licencia-maternidad/cron.log 2>&1
```

4. Use a service account with network access to SQL + Nodum.
5. Validate with `crontab -l` and monitor `cron.log` + `maternity_leave_sync.log`.

## 5. Monitoring

- Log file: `maternity_leave_sync.log` (rotates at 10 MB, 5 backups).
- Search for `CRITICAL`, `estado=0`, `Grabado Correctamente`, `Production check`.
- State file: `maternity_leave_sync_state.json` (per recurso watermark).

## 6. Security

- Restrict file ACL on `.env` to the run account only.
- Do not copy test `maternity_leave_sync_state.json` from another environment into production unless intentional.

## Exit codes (cron / scheduler)

| Code | Meaning |
|------|---------|
| 0 | OK / skipped (no work) |
| 1 | Config / production checks failed |
| 2 | SQL error |
| 3 | Nodum load failure |
