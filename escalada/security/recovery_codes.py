"""Emergency recovery codes for temporary admin USB override."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, TypedDict

STORE_FILE_NAME = "recovery_codes.json"
STORE_VERSION = 1
OVERRIDE_TTL_HOURS = 24

RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 5 * 60
BACKOFF_DELAYS_SECONDS = (0.25, 0.5, 1.0, 2.0)

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32

_store_lock = Lock()
_rate_lock = Lock()
_attempt_history_by_ip: dict[str, list[float]] = {}
_invalid_streak_by_ip: dict[str, int] = {}


class RecoveryStatus(TypedDict):
    recovery_override_active: bool
    recovery_override_until: datetime | None
    recovery_codes_remaining: int


class RecoveryRateLimitError(Exception):
    """Raised when recovery code attempts exceed the per-IP rate limit."""


class RecoveryOverrideActiveError(Exception):
    """Raised when override is already active and should not be extended."""

    def __init__(self, active_until: datetime):
        self.active_until = active_until
        super().__init__("override_already_active")


class RecoveryInvalidCodeError(Exception):
    """Raised when a provided recovery code is invalid or already used."""

    def __init__(self, backoff_seconds: float):
        self.backoff_seconds = backoff_seconds
        super().__init__("recovery_code_invalid")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_store(now_utc: datetime | None = None) -> dict[str, Any]:
    now = now_utc or _utcnow()
    return {
        "version": STORE_VERSION,
        "created_at": now.isoformat(),
        "override_ttl_hours": OVERRIDE_TTL_HOURS,
        "codes": [],
        "override": {
            "active_until": None,
            "activated_at": None,
            "activated_by_ip": None,
        },
    }


def _resolve_store_path() -> tuple[Path | None, str | None]:
    env_dir = (os.getenv("ESCALADA_SECRETS_DIR") or "").strip()
    if env_dir:
        try:
            secrets_dir = Path(env_dir).expanduser().resolve()
        except Exception:
            return None, "misconfigured"
        if secrets_dir.exists() and not secrets_dir.is_dir():
            return None, "misconfigured"
        return secrets_dir / STORE_FILE_NAME, None

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

    return secrets_dir / STORE_FILE_NAME, None


def get_recovery_store_path() -> Path:
    path, err = _resolve_store_path()
    if err or path is None:
        raise RuntimeError("recovery_store_path_misconfigured")
    return path


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_store(raw: Any) -> dict[str, Any]:
    store = _default_store()
    if not isinstance(raw, dict):
        return store

    created_at = raw.get("created_at")
    if isinstance(created_at, str) and created_at.strip():
        store["created_at"] = created_at

    ttl_hours = raw.get("override_ttl_hours")
    if isinstance(ttl_hours, int) and ttl_hours > 0:
        store["override_ttl_hours"] = ttl_hours

    codes = raw.get("codes")
    if isinstance(codes, list):
        normalized_codes: list[dict[str, Any]] = []
        for index, code_entry in enumerate(codes, start=1):
            if not isinstance(code_entry, dict):
                continue
            code_id = code_entry.get("code_id")
            code_hash = code_entry.get("hash")
            used_at = code_entry.get("used_at")
            if not isinstance(code_id, str) or not code_id.strip():
                code_id = f"rc_{index:03d}"
            if not isinstance(code_hash, str) or not code_hash.strip():
                continue
            normalized_codes.append(
                {
                    "code_id": code_id.strip(),
                    "hash": code_hash.strip(),
                    "used_at": used_at if isinstance(used_at, str) else None,
                }
            )
        store["codes"] = normalized_codes

    override = raw.get("override")
    if isinstance(override, dict):
        store["override"] = {
            "active_until": (
                override.get("active_until")
                if isinstance(override.get("active_until"), str)
                else None
            ),
            "activated_at": (
                override.get("activated_at")
                if isinstance(override.get("activated_at"), str)
                else None
            ),
            "activated_by_ip": (
                override.get("activated_by_ip")
                if isinstance(override.get("activated_by_ip"), str)
                else None
            ),
        }

    return store


def _load_store_no_lock() -> dict[str, Any]:
    path, err = _resolve_store_path()
    if err or path is None:
        return _default_store()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _default_store()
    except Exception:
        return _default_store()
    try:
        parsed = json.loads(raw)
    except Exception:
        return _default_store()
    return _normalize_store(parsed)


def load_recovery_store() -> dict[str, Any]:
    with _store_lock:
        return _load_store_no_lock()


def _save_store_no_lock(store: dict[str, Any]) -> None:
    path = get_recovery_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(_normalize_store(store), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def save_recovery_store_atomic(store: dict[str, Any]) -> None:
    with _store_lock:
        _save_store_no_lock(store)


def _normalize_code(value: str) -> str:
    cleaned = []
    for ch in str(value or "").upper():
        if ch in {" ", "-", "\t", "\n", "\r"}:
            continue
        if ch.isalnum():
            cleaned.append(ch)
    return "".join(cleaned)


def hash_recovery_code(code: str) -> str:
    normalized = _normalize_code(code)
    if not normalized:
        raise ValueError("empty_recovery_code")

    salt = os.urandom(16)
    digest = hashlib.scrypt(
        normalized.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${SCRYPT_DKLEN}${salt_b64}${digest_b64}"


def verify_recovery_code(code: str, hashed_value: str) -> bool:
    normalized = _normalize_code(code)
    if not normalized or not isinstance(hashed_value, str):
        return False

    parts = hashed_value.split("$")
    if len(parts) != 7 or parts[0] != "scrypt":
        return False
    try:
        n = int(parts[1])
        r = int(parts[2])
        p = int(parts[3])
        dklen = int(parts[4])
        salt = base64.urlsafe_b64decode(parts[5].encode("ascii"))
        expected = base64.urlsafe_b64decode(parts[6].encode("ascii"))
    except Exception:
        return False

    try:
        actual = hashlib.scrypt(
            normalized.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=dklen,
        )
    except Exception:
        return False
    return hmac.compare_digest(actual, expected)


def _normalize_ip(request_ip: str | None) -> str:
    value = (request_ip or "").strip()
    return value or "unknown"


def _consume_rate_limit_slot(request_ip: str, now_ts: float) -> None:
    with _rate_lock:
        history = [
            ts
            for ts in _attempt_history_by_ip.get(request_ip, [])
            if now_ts - ts < RATE_LIMIT_WINDOW_SECONDS
        ]
        if len(history) >= RATE_LIMIT_MAX_ATTEMPTS:
            _attempt_history_by_ip[request_ip] = history
            raise RecoveryRateLimitError("recovery_rate_limit")
        history.append(now_ts)
        _attempt_history_by_ip[request_ip] = history


def _register_invalid_attempt(request_ip: str) -> float:
    with _rate_lock:
        streak = _invalid_streak_by_ip.get(request_ip, 0) + 1
        _invalid_streak_by_ip[request_ip] = streak
    delay = BACKOFF_DELAYS_SECONDS[min(streak - 1, len(BACKOFF_DELAYS_SECONDS) - 1)]
    time.sleep(delay)
    return delay


def _register_success(request_ip: str) -> None:
    with _rate_lock:
        _invalid_streak_by_ip.pop(request_ip, None)


def get_remaining_codes_count(store: dict[str, Any] | None = None) -> int:
    source = _normalize_store(store) if store is not None else load_recovery_store()
    codes = source.get("codes")
    if not isinstance(codes, list):
        return 0
    return sum(
        1
        for item in codes
        if isinstance(item, dict) and item.get("used_at") in (None, "")
    )


def get_override_until(now_utc: datetime | None = None) -> datetime | None:
    now = now_utc.astimezone(timezone.utc) if now_utc else _utcnow()
    store = load_recovery_store()
    override = store.get("override") if isinstance(store, dict) else None
    if not isinstance(override, dict):
        return None
    parsed = _parse_iso_datetime(override.get("active_until"))
    if parsed is None or parsed <= now:
        return None
    return parsed


def is_override_active(now_utc: datetime | None = None) -> bool:
    return get_override_until(now_utc) is not None


def get_recovery_status(now_utc: datetime | None = None) -> RecoveryStatus:
    until = get_override_until(now_utc)
    return {
        "recovery_override_active": until is not None,
        "recovery_override_until": until,
        "recovery_codes_remaining": get_remaining_codes_count(),
    }


def consume_recovery_code(
    code: str,
    request_ip: str,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    now = now_utc.astimezone(timezone.utc) if now_utc else _utcnow()
    ip = _normalize_ip(request_ip)
    _consume_rate_limit_slot(ip, now.timestamp())

    normalized_code = _normalize_code(code)
    if not normalized_code:
        delay = _register_invalid_attempt(ip)
        raise RecoveryInvalidCodeError(delay)

    with _store_lock:
        store = _load_store_no_lock()
        ttl_hours = int(store.get("override_ttl_hours") or OVERRIDE_TTL_HOURS)
        if ttl_hours <= 0:
            ttl_hours = OVERRIDE_TTL_HOURS

        override = store.get("override")
        active_until = (
            _parse_iso_datetime(override.get("active_until"))
            if isinstance(override, dict)
            else None
        )
        if active_until is not None and active_until > now:
            raise RecoveryOverrideActiveError(active_until)

        matched_code: dict[str, Any] | None = None
        for code_entry in store.get("codes", []):
            if not isinstance(code_entry, dict):
                continue
            if code_entry.get("used_at"):
                continue
            code_hash = code_entry.get("hash")
            if not isinstance(code_hash, str):
                continue
            if verify_recovery_code(normalized_code, code_hash):
                matched_code = code_entry
                break

        if matched_code is not None:
            matched_code["used_at"] = now.isoformat()
            override_until = now + timedelta(hours=ttl_hours)
            store["override"] = {
                "active_until": override_until.isoformat(),
                "activated_at": now.isoformat(),
                "activated_by_ip": ip,
            }
            _save_store_no_lock(store)
            remaining = get_remaining_codes_count(store)
            _register_success(ip)
            return {
                "ok": True,
                "override_until": override_until,
                "remaining": remaining,
                "code_id": str(matched_code.get("code_id") or ""),
            }

    delay = _register_invalid_attempt(ip)
    raise RecoveryInvalidCodeError(delay)


def reset_runtime_state() -> None:
    """Test helper: clear in-memory rate-limit and backoff state."""
    with _rate_lock:
        _attempt_history_by_ip.clear()
        _invalid_streak_by_ip.clear()
