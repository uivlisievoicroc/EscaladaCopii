# RUN (LAN Production)

## 1) Start server on admin laptop
Run the packaged binary on the host laptop.

- Windows: double click `EscaladaServer.exe`
- macOS/Linux: run `./EscaladaServer` from terminal

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

## 4) USB admin security behavior
- USB key is **not required for server startup**.
- USB key **is required for admin-protected mutating actions** (unlock flow).
- Judge/public read-only usage remains available without USB unlock.

### USB secret (required for validation)
Packaged runs must have `USB_LICENSE_SECRET` available so the server can validate `competition.key` on the stick.

Recommended (persistent, no terminal export): create a 1-line file in app-data:
- macOS: `~/Library/Application Support/EscaladaServer/secrets/usb_license_secret.txt`
- Windows: `%APPDATA%\\EscaladaServer\\secrets\\usb_license_secret.txt`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/EscaladaServer/secrets/usb_license_secret.txt`

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
