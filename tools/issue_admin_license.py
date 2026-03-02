#!/usr/bin/env python3
"""Issue an offline Ed25519-signed admin license JWT."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ISSUER = "escalada"
AUDIENCE = "escalada-admin"
DEFAULT_KID = "default"


def _resolve_default_output_path() -> Path:
    env_dir = (os.getenv("ESCALADA_SECRETS_DIR") or "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve() / "admin_license.jwt"

    home = Path.home()
    if sys.platform.startswith("win"):
        base = Path(os.getenv("APPDATA") or (home / "AppData" / "Roaming"))
        secrets_dir = base / "EscaladaServer" / "secrets"
    elif sys.platform == "darwin":
        secrets_dir = (
            home / "Library" / "Application Support" / "EscaladaServer" / "secrets"
        )
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or (home / ".local" / "share"))
        secrets_dir = base / "EscaladaServer" / "secrets"
    return secrets_dir / "admin_license.jwt"


def _parse_expiry(value: str) -> int:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("expires_at_required")
    if raw.isdigit():
        return int(raw)

    normalized = raw.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp())


def _load_private_key(private_key_path: Path) -> Ed25519PrivateKey:
    pem = private_key_path.read_bytes()
    loaded = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(loaded, Ed25519PrivateKey):
        raise ValueError("private_key_must_be_ed25519")
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue signed admin_license.jwt")
    parser.add_argument(
        "--private-key", required=True, help="Path to Ed25519 private key PEM."
    )
    parser.add_argument(
        "--expires-at",
        required=True,
        help="UTC expiry: ISO-8601 (e.g. 2026-12-31T23:59:59Z) or unix seconds.",
    )
    parser.add_argument("--license-id", default="", help="Optional UUID string.")
    parser.add_argument("--kid", default=DEFAULT_KID, help="Key id in JWT header.")
    parser.add_argument("--note", default="", help="Optional license note.")
    parser.add_argument("--out", default="", help="Output JWT path.")
    args = parser.parse_args()

    private_key_path = Path(args.private_key).expanduser().resolve()
    if not private_key_path.is_file():
        print(f"Error: private key not found: {private_key_path}", file=sys.stderr)
        return 1

    try:
        private_key = _load_private_key(private_key_path)
    except Exception as exc:
        print(f"Error: failed to load private key ({exc}).", file=sys.stderr)
        return 1

    try:
        exp_ts = _parse_expiry(args.expires_at)
    except Exception as exc:
        print(f"Error: invalid --expires-at ({exc}).", file=sys.stderr)
        return 1

    now_ts = int(datetime.now(timezone.utc).timestamp())
    if exp_ts <= now_ts:
        print("Error: --expires-at must be in the future.", file=sys.stderr)
        return 1

    license_id = (args.license_id or "").strip() or str(uuid.uuid4())
    kid = (args.kid or "").strip() or DEFAULT_KID
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now_ts,
        "exp": exp_ts,
        "license_id": license_id,
    }
    note = (args.note or "").strip()
    if note:
        payload["note"] = note

    token = jwt.encode(
        payload,
        key=private_key,
        algorithm="EdDSA",
        headers={"kid": kid},
    )

    output_path = (
        Path(args.out).expanduser().resolve()
        if (args.out or "").strip()
        else _resolve_default_output_path()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{token}\n", encoding="utf-8")
    try:
        os.chmod(output_path, 0o600)
    except Exception:
        pass

    expires_iso = datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat()
    print(f"Issued admin license: {output_path}")
    print(f"license_id: {license_id}")
    print(f"kid: {kid}")
    print(f"expires_at: {expires_iso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
