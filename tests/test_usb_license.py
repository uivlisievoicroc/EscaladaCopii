from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from escalada.security import usb_license


@pytest.fixture(autouse=True)
def reset_usb_license_cache(monkeypatch):
    monkeypatch.setattr(usb_license, "_cached_result", None)
    monkeypatch.setattr(usb_license, "_cached_at_monotonic", 0.0)


def _status(valid: bool, reason: str) -> dict:
    return {
        "valid": valid,
        "reason": reason,
        "mountpoint": "/media/test-usb" if valid else None,
        "checked_at": datetime.now(timezone.utc),
    }


def test_check_license_valid_signature(monkeypatch):
    mountpoint = "/media/test-usb"
    fs_name = "vfat"
    total_bytes = 64 * 1024 * 1024
    secret = "unit-test-secret"

    partition = SimpleNamespace(mountpoint=mountpoint, fstype=fs_name)
    fake_psutil = SimpleNamespace(
        disk_partitions=lambda all=False: [partition],
        disk_usage=lambda _mountpoint: SimpleNamespace(total=total_bytes),
    )

    expected = usb_license.build_expected_key(
        fs_name=fs_name,
        total_bytes=total_bytes,
        secret=secret,
    )

    monkeypatch.setenv("USB_LICENSE_SECRET", secret)
    monkeypatch.setattr(usb_license, "psutil", fake_psutil)
    monkeypatch.setattr(usb_license, "_is_candidate_partition", lambda _part: True)

    def fake_is_file(path: Path) -> bool:
        return str(path) == f"{mountpoint}/competition.key"

    def fake_read_text(path: Path, encoding: str = "utf-8") -> str:
        if str(path) == f"{mountpoint}/competition.key":
            return expected
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(Path, "is_file", fake_is_file, raising=False)
    monkeypatch.setattr(Path, "read_text", fake_read_text, raising=False)

    result = usb_license.check_license(force_refresh=True)

    assert result["valid"] is True
    assert result["reason"] == "ok"
    assert result["mountpoint"] == mountpoint


def test_check_license_invalid_signature(monkeypatch):
    mountpoint = "/media/test-usb"
    fs_name = "vfat"
    total_bytes = 32 * 1024 * 1024
    secret = "unit-test-secret"

    partition = SimpleNamespace(mountpoint=mountpoint, fstype=fs_name)
    fake_psutil = SimpleNamespace(
        disk_partitions=lambda all=False: [partition],
        disk_usage=lambda _mountpoint: SimpleNamespace(total=total_bytes),
    )

    monkeypatch.setenv("USB_LICENSE_SECRET", secret)
    monkeypatch.setattr(usb_license, "psutil", fake_psutil)
    monkeypatch.setattr(usb_license, "_is_candidate_partition", lambda _part: True)

    def fake_is_file(path: Path) -> bool:
        return str(path) == f"{mountpoint}/competition.key"

    def fake_read_text(path: Path, encoding: str = "utf-8") -> str:
        if str(path) == f"{mountpoint}/competition.key":
            return "deadbeef"
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(Path, "is_file", fake_is_file, raising=False)
    monkeypatch.setattr(Path, "read_text", fake_read_text, raising=False)

    result = usb_license.check_license(force_refresh=True)

    assert result["valid"] is False
    assert result["reason"] == "invalid_signature"


def test_check_license_reports_misconfigured_without_secret(monkeypatch):
    monkeypatch.delenv("USB_LICENSE_SECRET", raising=False)
    monkeypatch.setattr(usb_license, "_load_usb_secret_from_file", lambda: "")

    result = usb_license.check_license(force_refresh=True)

    assert result["valid"] is False
    assert result["reason"] == "misconfigured"


def test_check_license_uses_ttl_cache(monkeypatch):
    calls = {"count": 0}

    def fake_scan() -> dict:
        calls["count"] += 1
        return _status(True, "ok")

    monkeypatch.setattr(usb_license, "_scan_license", fake_scan)

    first = usb_license.check_license(force_refresh=True)
    second = usb_license.check_license()

    assert calls["count"] == 1
    assert first["checked_at"] == second["checked_at"]
