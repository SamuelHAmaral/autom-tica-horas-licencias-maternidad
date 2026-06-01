# Production deployment checklist

Use this before scheduling the job on the production server.

## 1. Environment file (`.env`)

Copy `.env.example` to `.env` on the server. **Never commit `.env`.**

| Setting | Production value |
|---------|----------------|
| `SYNC_PRODUCTION` | `1` (blocks dry-run / test date) |
| `NODUM_DRY_RUN` | `0` |
| `NODUM_PARTE_SCOPE` | `today` (daily task; use `backfill` only for one-time catch-up) |
| `NODUM_WSDL_URL` | `http://<host>:8080/soap/Amaral01/services/forms/v1.3/TpryParteDiaGS?wsdl` |
| `NODUM_READ_WSDL_URL` | `http://<host>:8080/soap/Amaral01/services/sim/v1.3/RPryConsHorsxTit?wsdl` |
| `NODUM_READ_OPERATION` | `simular` |
| `NODUM_READ_MATCH_RESOLVED_PROYECTO` | `1` |
| `AMARAL_CATALOG_DATABASE` | `amaral01` |
| `SYNC_TEST_DATE` | **unset** |
| `SYNC_FORCE_RUN` | **unset** (unless manual run on holiday) |

Confirm SQL points at production RRHH (`SQL_SERVER_*`) and Nodum credentials have access to **Amaral01** forms + sim services.

## 2. One-time catch-up vs daily

1. **Initial catch-up** (optional): `NODUM_PARTE_SCOPE=backfill`, run once, verify logs and Nodum UI.
2. **Daily production**: set `NODUM_PARTE_SCOPE=today`, keep `maternity_leave_sync_state.json` on the server (gitignored; watermark for backfill if you switch scope again).

## 3. Pre-flight test on the server

```powershell
cd "C:\path\to\automática horas licencias maternidad 1"
py -3 scripts\audit_maternity_sql.py
py -3 main.py
```

- Exit code **0** = success or nothing to do (weekend/holiday/already synced).
- Exit code **3** = Nodum rejected a load; check `maternity_leave_sync.log`.
- Audit script lists who is in active maternal leave and resolved `G2.CentrodeCosto`.

## 4. Windows Task Scheduler

1. Create task: **Daily**, weekday mornings (after HR data is current).
2. Action: `run_daily_sync.bat` (or `py -3 main.py`).
3. **Start in**: project folder (where `.env` lives).
4. Run whether user is logged on or not; use a service account with network access to SQL + Nodum.
5. On failure, alert if **Last Run Result** ≠ `0x0` (see exit codes in README).

## 5. Monitoring

- Log file: `maternity_leave_sync.log` (rotates at 10 MB, 5 backups).
- Search for `CRITICAL`, `estado=0`, `Grabado Correctamente`, `Production check`.
- State file: `maternity_leave_sync_state.json` (per recurso watermark).

## 6. Security

- Restrict file ACL on `.env` to the run account only.
- Do not copy test `maternity_leave_sync_state.json` from another environment into production unless intentional.

## Exit codes (Task Scheduler)

| Code | Meaning |
|------|---------|
| 0 | OK / skipped (no work) |
| 1 | Config / production checks failed |
| 2 | SQL error |
| 3 | Nodum load failure |
