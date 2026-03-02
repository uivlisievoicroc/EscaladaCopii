"""Offline admin license verification (Ed25519 JWT)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import TypedDict

import jwt

try:
    from cryptography.hazmat.primitives import serialization
except Exception:  # pragma: no cover - runtime dependency guard
    serialization = None

_CACHE_TTL_SEC = 1.0
_cache_lock = Lock()
_cached_result: "AdminLicenseStatus | None" = None
_cached_at_monotonic = 0.0

LICENSE_FILE_NAME = "admin_license.jwt"
DEFAULT_KID = (os.getenv("ADMIN_LICENSE_DEFAULT_KID") or "default").strip() or "default"
GRACE_PERIOD_HOURS = 24
EXPECTED_ISSUER = "escalada"
EXPECTED_AUDIENCE = "escalada-admin"

# Embedded default public key for offline verification. Can be overridden by env vars.
PUBLIC_KEYS_PEM_BY_KID: dict[str, str] = {
    "default": (
        "-----BEGIN PUBLIC KEY-----\n"
        "MCowBQYDK2VwAyEA1OejiVMDlFBxzidB680hZD6zLtYumsO3icaC/6ZQeuE=\n"
        "-----END PUBLIC KEY-----\n"
    ),
}


class AdminLicenseStatus(TypedDict):
    valid: bool
    reason: str
    checked_at: datetime
    expires_at: datetime | None
    in_grace: bool
    grace_until: datetime | None
    license_id: str | None
    kid: str | None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_status(
    *,
    valid: bool,
    reason: str,
    checked_at: datetime,
    expires_at: datetime | None = None,
    in_grace: bool = False,
    grace_until: datetime | None = None,
    license_id: str | None = None,
    kid: str | None = None,
) -> AdminLicenseStatus:
    return {
        "valid": valid,
        "reason": reason,
        "checked_at": checked_at,
        "expires_at": expires_at,
        "in_grace": in_grace,
        "grace_until": grace_until,
        "license_id": license_id,
        "kid": kid,
    }


def _resolve_license_path() -> tuple[Path | None, str | None]:
    env_dir = (os.getenv("ESCALADA_SECRETS_DIR") or "").strip()
    if env_dir:
        try:
            secrets_dir = Path(env_dir).expanduser().resolve()
        except Exception:
            return None, "misconfigured"
        if secrets_dir.exists() and not secrets_dir.is_dir():
            return None, "misconfigured"
        return secrets_dir / LICENSE_FILE_NAME, None

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

    return secrets_dir / LICENSE_FILE_NAME, None


def _load_public_keys() -> tuple[dict[str, str] | None, str | None]:
    key_map = {
        str(k).strip(): str(v).strip()
        for k, v in PUBLIC_KEYS_PEM_BY_KID.items()
        if str(k).strip() and str(v).strip()
    }

    default_override = (os.getenv("ADMIN_LICENSE_PUBLIC_KEY_PEM") or "").strip()
    if default_override:
        key_map[DEFAULT_KID] = default_override

    raw_map = (os.getenv("ADMIN_LICENSE_PUBLIC_KEYS_PEM_BY_KID") or "").strip()
    if raw_map:
        try:
            parsed = json.loads(raw_map)
        except Exception:
            return None, "misconfigured"
        if not isinstance(parsed, dict):
            return None, "misconfigured"
        for kid, pem in parsed.items():
            kid_value = str(kid).strip()
            pem_value = str(pem).strip() if isinstance(pem, str) else ""
            if kid_value and pem_value:
                key_map[kid_value] = pem_value

    if not key_map:
        return None, "misconfigured"

    return key_map, None


def _load_public_key(pem: str):
    if serialization is None:
        return None
    try:
        return serialization.load_pem_public_key(pem.encode("utf-8"))
    except Exception:
        return None


def _scan_admin_license(now_utc: datetime) -> AdminLicenseStatus:
    license_path, path_error = _resolve_license_path()
    if path_error:
        return _build_status(valid=False, reason=path_error, checked_at=now_utc)
    if license_path is None:
        return _build_status(valid=False, reason="misconfigured", checked_at=now_utc)

    try:
        token = license_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return _build_status(valid=False, reason="not_found", checked_at=now_utc)
    except Exception:
        return _build_status(valid=False, reason="misconfigured", checked_at=now_utc)

    if not token:
        return _build_status(valid=False, reason="invalid_format", checked_at=now_utc)

    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        return _build_status(valid=False, reason="invalid_format", checked_at=now_utc)

    header_kid = header.get("kid")
    requested_kid = (
        header_kid.strip()
        if isinstance(header_kid, str) and header_kid.strip()
        else None
    )

    key_map, keys_error = _load_public_keys()
    if keys_error or not key_map:
        return _build_status(valid=False, reason="misconfigured", checked_at=now_utc)

    if requested_kid:
        selected_kid = requested_kid
        public_key_pem = key_map.get(selected_kid)
        if not public_key_pem:
            return _build_status(
                valid=False,
                reason="invalid_signature",
                checked_at=now_utc,
                kid=selected_kid,
            )
    else:
        selected_kid = DEFAULT_KID
        public_key_pem = key_map.get(selected_kid)
        if not public_key_pem:
            return _build_status(
                valid=False,
                reason="misconfigured",
                checked_at=now_utc,
                kid=selected_kid,
            )

    public_key = _load_public_key(public_key_pem)
    if public_key is None:
        return _build_status(
            valid=False,
            reason="misconfigured",
            checked_at=now_utc,
            kid=selected_kid,
        )

    try:
        payload = jwt.decode(
            token,
            key=public_key,
            algorithms=["EdDSA"],
            audience=EXPECTED_AUDIENCE,
            issuer=EXPECTED_ISSUER,
            options={"verify_exp": False},
        )
    except jwt.InvalidSignatureError:
        return _build_status(
            valid=False,
            reason="invalid_signature",
            checked_at=now_utc,
            kid=selected_kid,
        )
    except jwt.InvalidTokenError:
        return _build_status(
            valid=False,
            reason="invalid_claims",
            checked_at=now_utc,
            kid=selected_kid,
        )

    exp = payload.get("exp")
    iat = payload.get("iat")
    license_id = payload.get("license_id")
    if not isinstance(exp, (int, float)) or not isinstance(iat, (int, float)):
        return _build_status(
            valid=False,
            reason="invalid_claims",
            checked_at=now_utc,
            kid=selected_kid,
        )
    if not isinstance(license_id, str) or not license_id.strip():
        return _build_status(
            valid=False,
            reason="invalid_claims",
            checked_at=now_utc,
            kid=selected_kid,
        )

    expires_at = datetime.fromtimestamp(float(exp), tz=timezone.utc)
    grace_until = expires_at + timedelta(hours=GRACE_PERIOD_HOURS)
    if now_utc <= expires_at:
        return _build_status(
            valid=True,
            reason="ok",
            checked_at=now_utc,
            expires_at=expires_at,
            in_grace=False,
            grace_until=grace_until,
            license_id=license_id.strip(),
            kid=selected_kid,
        )
    if now_utc <= grace_until:
        return _build_status(
            valid=True,
            reason="grace",
            checked_at=now_utc,
            expires_at=expires_at,
            in_grace=True,
            grace_until=grace_until,
            license_id=license_id.strip(),
            kid=selected_kid,
        )

    return _build_status(
        valid=False,
        reason="expired",
        checked_at=now_utc,
        expires_at=expires_at,
        in_grace=False,
        grace_until=grace_until,
        license_id=license_id.strip(),
        kid=selected_kid,
    )


def check_admin_license(
    force_refresh: bool = False,
    now_utc: datetime | None = None,
) -> AdminLicenseStatus:
    """Return cached admin-license status unless force_refresh is requested."""
    global _cached_result, _cached_at_monotonic
    if now_utc is None:
        now_monotonic = monotonic()
        with _cache_lock:
            if (
                not force_refresh
                and _cached_result is not None
                and now_monotonic - _cached_at_monotonic < _CACHE_TTL_SEC
            ):
                return dict(_cached_result)

    check_at = now_utc.astimezone(timezone.utc) if now_utc else _utcnow()
    result = _scan_admin_license(check_at)

    if now_utc is None:
        with _cache_lock:
            _cached_result = result
            _cached_at_monotonic = monotonic()

    return dict(result)
