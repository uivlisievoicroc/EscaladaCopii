# Escalada Backend (FastAPI)

Real-time climbing competition management backend using FastAPI + WebSockets.

## Storage

This repo runs in **JSON storage mode only** (no Postgres/Docker).

- Optional: `STORAGE_DIR=./data` (default: `data`)
- Startup behavior: by default, the server starts **clean** (clears persisted box states). To keep state across restarts, set `RESET_BOXES_ON_START=0`.
- Run a single worker: `--workers 1`

## Quick Start

```bash
poetry install
poetry run pip install -e ../escalada-core

export STORAGE_DIR=./data
# Optional: keep state across restarts
# export RESET_BOXES_ON_START=0
poetry run uvicorn escalada.main:app --host 0.0.0.0 --port 8000 --workers 1
```

## Production Safety Checks

In production (`ENV=production` or `APP_ENV=production`), startup fails fast when unsafe defaults are used:

- `JWT_SECRET` missing or equal to `dev-secret-change-me`

Set a strong `JWT_SECRET` before starting the API.

## Trusted Network Admin (no username/password)

Admin endpoints no longer use username/password login.

- If a request has a valid JWT, role checks work exactly as before.
- If a request has no JWT and source IP is trusted, backend grants synthetic admin claims (`trusted-admin`).
- Trusted IP allowlist is configured with `ADMIN_TRUSTED_IPS` (comma-separated, default: `127.0.0.1,::1,localhost`).

Do not expose the API publicly without network protections (reverse proxy allowlists, VPN, firewall), because trusted IPs bypass admin login.

## USB admin security (Lock/Unlock)

Admin actions now require a second local factor (USB key) in addition to existing RBAC/JWT checks.

- `USB_LICENSE_SECRET` (required for valid USB checks)
  - If missing, backend still starts, but license status is reported as `misconfigured` and admin USB unlock cannot succeed.
- `USB_WATCHDOG_INTERVAL_SEC` (optional, default `5`)
  - Background watchdog interval for auto-lock when USB license becomes invalid.

### New endpoints

- `GET /api/license/status`
  - Returns `license_valid`, `license_reason`, `admin_unlocked` (and non-sensitive metadata).
- `POST /api/admin/unlock`
  - Requires admin RBAC.
  - Validates USB license and issues an in-memory USB admin session token.
  - Returns `403` with `{"code":"LICENSE_REQUIRED"}` when USB is missing/invalid.
- `POST /api/admin/lock`
  - Requires admin RBAC.
  - Revokes the USB admin session token immediately.
- `GET /api/license/events` (SSE)
  - Emits `license_status_changed` and `admin_locked`.

### Enforcement model

- All `/api/admin/*` routes require:
  - admin RBAC, and
  - valid USB admin session token in `Authorization: Bearer <usb_admin_token>`, and
  - currently valid USB license.
- `POST /api/save_ranking` also requires USB admin lock.
- `POST /api/cmd` enforces USB admin lock only for admin callers and mutating command types; judge flow remains unaffected.
- If USB is removed while unlocked, watchdog auto-locks in at most `USB_WATCHDOG_INTERVAL_SEC`.

### Provisioning `competition.key` on USB

Use the provisioning script to generate/write the root file expected by the validator:

```bash
# Set USB_LICENSE_SECRET either via `.env` (recommended) or environment.
# (The script loads `.env` automatically if present.)
# export USB_LICENSE_SECRET='replace-with-strong-secret'
poetry run python tools/provision_usb_key.py <mountpoint>
```

Examples:
- macOS: `<mountpoint>` like `/Volumes/MY_USB`
- Linux: `<mountpoint>` like `/media/<user>/MY_USB` or `/run/media/<user>/MY_USB`
- Windows: `<mountpoint>` like `E:\\`

The script writes `<mountpoint>/competition.key` and asks for confirmation before overwrite (or pass `--force`).

## Tests

```bash
poetry install
poetry run pip install -e ../escalada-core
poetry run pytest tests -q
```

## Backup & restore (ops)

- Backup JSON (single box): `GET /api/admin/backup/box/{boxId}`
- Backup JSON (all boxes): `GET /api/admin/backup/full`
- Restore din backup: `POST /api/admin/restore` cu payload `{"snapshots":[...]}`
- Periodic backups: controlate de `BACKUP_INTERVAL_MIN`, `BACKUP_RETENTION_FILES`, `BACKUP_DIR`

## CI notes

- Workflow-ul de CI instalează `escalada-core` din repo separat; dacă `escalada-core` este privat, setează secretul `ESCALADA_CORE_TOKEN` în GitHub Actions (PAT cu access read la `escalada-core`).

## Formatting & Hooks

Python formatting is enforced via pre-commit with Black and isort.

```bash
poetry run pre-commit run --all-files
```
