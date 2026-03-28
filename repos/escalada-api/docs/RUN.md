# RUN (LAN Production)

## 1) Start server on admin laptop
Run the packaged binary on the host laptop.

- Windows: double click `Start EscaladaServer.bat` (recommended, if included) or `EscaladaServer.exe`
- macOS/Linux: run `./EscaladaServer` from terminal

### Windows: Double-click start (recommended)
If your release zip includes `Start EscaladaServer.bat`:
1. Unzip the release.
2. Double-click `Start EscaladaServer.bat`.
3. Keep the console window open during the competition.

This launcher:
- starts `EscaladaServer.exe`
- detects the selected port in range `8000..8100`
- opens the browser on the laptop LAN IP (important for QR links)

### macOS: Double-click start (recommended)
If your release zip includes `Start EscaladaServer.command`:
1. Unzip the release.
2. Right click `Start EscaladaServer.command` → `Open` (first run, unsigned).
3. Keep the Terminal window open during the competition.

This launcher:
- starts `EscaladaServer`
- detects the selected port in range `8000..8100`
- opens the browser on the laptop LAN IP (important for QR links)

The server binds `0.0.0.0` and tries ports in range `8000..8100`.
If `8000` is busy, logs show:
`Port 8000 busy -> using <port>`

Runtime info endpoint:
`GET /api/runtime`

## 2) Find LAN URL for judges/public
Use the laptop LAN IP and runtime port.

- Windows: `ipconfig`
- macOS: `ipconfig getifaddr en0` (or active interface)
- Linux: `hostname -I`

Open:
`http://<LAN_IP>:<PORT>/`

## 3) First-run prompts (important)

### Windows Defender Firewall
Symptom:
`Windows Defender Firewall has blocked some features of this app`.

Action:
1. Keep `Private networks` checked.
2. Click `Allow access`.
3. Do not expose on Public network unless explicitly needed.

### macOS Gatekeeper (unsigned app)
Symptoms:
- `“EscaladaServer” can’t be opened because Apple cannot check it for malicious software`
- `developer cannot be verified`

Action:
1. Right click app/binary.
2. Click `Open`.
3. Confirm `Open` again in the warning dialog.

## 4) Admin security behavior (USB + emergency recovery + offline license)
- USB key is **not required for server startup**.
- Admin actions follow Policy A:
  `admin_unlocked && admin_license_valid && (usb_license_valid || recovery_override_active)`
- Judge/public read-only usage remains unaffected.

### USB secret (required for validation)
Packaged runs must have `USB_LICENSE_SECRET` available so the server can validate `competition.key` on the stick.

Recommended (persistent, no terminal export): create a 1-line file in app-data:
- macOS: `~/Library/Application Support/EscaladaServer/secrets/usb_license_secret.txt`
- Windows: `%APPDATA%\\EscaladaServer\\secrets\\usb_license_secret.txt`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/EscaladaServer/secrets/usb_license_secret.txt`

### Admin license file (required for admin flows)
Place `admin_license.jwt` in secrets dir:
- macOS: `~/Library/Application Support/EscaladaServer/secrets/admin_license.jwt`
- Windows: `%APPDATA%\\EscaladaServer\\secrets\\admin_license.jwt`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/EscaladaServer/secrets/admin_license.jwt`

Issue it offline using:
`poetry run python tools/issue_admin_license.py --private-key /path/to/ed25519_private.pem --expires-at 2026-12-31T23:59:59Z --kid default`

### Recovery codes file (break-glass)
Generate once and keep on paper:
`poetry run python tools/generate_recovery_codes.py`

This writes `recovery_codes.json` in `ESCALADA_SECRETS_DIR` with hashed one-time codes only.

Emergency override rules:
- Override lasts 24h.
- Override does not auto-extend if already active.
- Rate limit is 5 attempts / 5 min / IP (in-memory; server restart resets counters).
- Invalid attempts use incremental backoff.
- Audit logs store outcome/IP/timestamp/`code_id`; never the code plaintext.

## 5) QR workflow
From Control Panel:
1. Generate judge QR links for each box.
2. Generate public hub QR.
3. Judges/public open links on phone via venue LAN.

## 6) Data location (persistent app-data)
Data is stored in user app-data, not in current working directory.

- Windows: `%APPDATA%/EscaladaServer`
- macOS: `~/Library/Application Support/EscaladaServer`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/EscaladaServer`

Subfolders:
- `storage/` JSON + NDJSON
- `backups/` backup snapshots
- `logs/` runtime logs
- `exports/clasamente/` ranking exports
- `secrets/` persistent local secrets

## 7) Backup and restore
- Back up the whole app-data directory before/after competition.
- Restore by replacing app-data directory with a known-good backup.
- Keep timestamped backups outside the laptop as well (USB/external disk).

## 8) Legacy migration (one-time)
On first packaged start:
1. Timestamped backup is created.
2. Legacy data is copied from local paths.
3. Copy result is verified.
4. `migration_done.json` marker is written.
5. Legacy paths are renamed to `*.legacy.<timestamp>` (not deleted).
