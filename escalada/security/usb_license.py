"""USB license verification with short-lived cache."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import TypedDict

try:
    import psutil
except Exception:  # pragma: no cover - handled at runtime
    psutil = None

_CACHE_TTL_SEC = 1.0
_cache_lock = Lock()
_cached_result: "LicenseStatus | None" = None
_cached_at_monotonic = 0.0


class LicenseStatus(TypedDict):
    valid: bool
    reason: str
    mountpoint: str | None
    checked_at: datetime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_status(valid: bool, reason: str, mountpoint: str | None) -> LicenseStatus:
    return {
        "valid": valid,
        "reason": reason,
        "mountpoint": mountpoint,
        "checked_at": _utcnow(),
    }


def _js_like_round(value: float) -> int:
    return int(value + 0.5)


def build_expected_key(*, fs_name: str, total_bytes: int, secret: str) -> str:
    """Build the expected `competition.key` content for the given filesystem metadata."""
    fs_name_safe = (fs_name or "").strip()
    magic_number = _js_like_round(total_bytes / 1024.0)
    salt_input = f"B-PRO-{magic_number}-{len(fs_name_safe)}-{secret}".encode("utf-8")
    dynamic_salt = hashlib.sha256(salt_input).digest()
    stick_id = f"{fs_name_safe}-{int(total_bytes)}".encode("utf-8")
    return hmac.new(dynamic_salt, stick_id, hashlib.sha256).hexdigest()


def _windows_drive_type(mountpoint: str) -> int | None:
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes

        return int(ctypes.windll.kernel32.GetDriveTypeW(mountpoint))
    except Exception:
        return None


def _is_candidate_partition(partition) -> bool:
    mountpoint = (partition.mountpoint or "").strip()
    if not mountpoint:
        return False

    if sys.platform == "darwin":
        return mountpoint.startswith("/Volumes/")

    if sys.platform.startswith("linux"):
        return mountpoint.startswith("/media/") or mountpoint.startswith("/run/media/")

    if sys.platform.startswith("win"):
        if not re.match(r"^[A-Za-z]:\\$", mountpoint):
            return False
        if mountpoint.upper() == "C:\\":
            return False
        drive_type = _windows_drive_type(mountpoint)
        if drive_type is None:
            return True
        # DRIVE_REMOVABLE (2)
        return drive_type == 2

    return False


def _scan_license() -> LicenseStatus:
    secret = (os.getenv("USB_LICENSE_SECRET") or "").strip()
    if not secret:
        return _build_status(False, "misconfigured", None)

    if psutil is None:
        return _build_status(False, "error", None)

    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception:
        return _build_status(False, "error", None)

    candidates = []
    seen: set[str] = set()
    for partition in partitions:
        if not _is_candidate_partition(partition):
            continue
        mountpoint = (partition.mountpoint or "").strip()
        if mountpoint in seen:
            continue
        seen.add(mountpoint)
        candidates.append(partition)

    found_invalid_signature = False
    for partition in candidates:
        mountpoint = (partition.mountpoint or "").strip()
        if not mountpoint:
            continue
        key_path = Path(mountpoint) / "competition.key"
        try:
            if not key_path.is_file():
                continue
        except Exception:
            continue

        try:
            file_content = key_path.read_text(encoding="utf-8").strip()
            fs_name = (partition.fstype or "").strip()
            total_bytes = int(psutil.disk_usage(mountpoint).total)
            expected = build_expected_key(fs_name=fs_name, total_bytes=total_bytes, secret=secret)
            if hmac.compare_digest(file_content.lower(), expected.lower()):
                return _build_status(True, "ok", mountpoint)
            found_invalid_signature = True
        except Exception:
            continue

    if found_invalid_signature:
        return _build_status(False, "invalid_signature", None)
    return _build_status(False, "not_found", None)


def check_license(force_refresh: bool = False) -> LicenseStatus:
    """Return cached USB license status (TTL=1s) unless force_refresh is requested."""
    global _cached_result, _cached_at_monotonic
    now = monotonic()
    with _cache_lock:
        if (
            not force_refresh
            and _cached_result is not None
            and now - _cached_at_monotonic < _CACHE_TTL_SEC
        ):
            return dict(_cached_result)

    result = _scan_license()
    with _cache_lock:
        _cached_result = result
        _cached_at_monotonic = monotonic()
    return dict(result)

