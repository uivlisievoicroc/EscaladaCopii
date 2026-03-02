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

## Admin Security (USB + Emergency Recovery + Offline License)

Admin actions use Policy A:

`admin_unlocked && admin_license_valid && (usb_license_valid || recovery_override_active)`

Judge/public flows are unchanged.

- `USB_LICENSE_SECRET` (required for valid USB checks)
  - If missing, backend still starts, but USB status is `misconfigured` and USB checks fail.
- `USB_WATCHDOG_INTERVAL_SEC` (optional, default `5`)
  - Background watchdog for lock safety.
- `ESCALADA_SECRETS_DIR/admin_license.jwt`
  - Offline Ed25519-signed JWT required for admin flows.
- `ESCALADA_SECRETS_DIR/recovery_codes.json`
  - Hash-only one-time recovery codes and emergency override state.

### Security endpoints

- `GET /api/license/status`
  - Returns USB status, unlock state, admin license status, and recovery override status:
    `admin_license_valid`, `admin_license_reason`, `admin_license_expires_at`,
    `admin_license_in_grace`, `admin_license_grace_until`, `admin_license_id`,
    `recovery_override_active`, `recovery_override_until`, `recovery_codes_remaining`.
- `POST /api/admin/unlock`
  - Requires admin RBAC.
  - Requires valid admin license.
  - Unlock succeeds when `(USB valid OR recovery override active)`.
- `POST /api/admin/lock`
  - Requires admin RBAC.
  - Revokes the admin unlock token immediately.
- `POST /api/admin/recovery/consume`
  - Requires admin RBAC + trusted admin IP.
  - Requires valid admin license.
  - Consumes one recovery code one-time and activates override for 24h.
  - Errors: `RECOVERY_CODE_INVALID`, `OVERRIDE_ALREADY_ACTIVE`, `RECOVERY_RATE_LIMIT`.
- `GET /api/license/events` (SSE)
  - Emits `license_status_changed` and `admin_locked`.

### Emergency recovery behavior

- One-time codes are stored hashed only (never plaintext).
- Override TTL is fixed at 24h and is not auto-extended when already active.
- Brute-force protection:
  - Rate limit: max 5 attempts / 5 min / IP (in-memory, resets on server restart).
  - Incremental backoff on invalid attempts.
- Audit logging records outcome + IP + timestamp + `code_id` (when available), never the code itself.

### Provisioning admin license JWT

Issue a signed license file from an offline trusted machine:

```bash
poetry run python tools/issue_admin_license.py \
  --private-key /path/to/ed25519_private.pem \
  --expires-at 2026-12-31T23:59:59Z \
  --kid default
```

The tool writes `admin_license.jwt` in `ESCALADA_SECRETS_DIR` by default.

### Generate recovery codes

```bash
poetry run python tools/generate_recovery_codes.py
```

The tool prints codes once (`PRINT THESE ON PAPER`) and writes only hashes to `recovery_codes.json`.

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
