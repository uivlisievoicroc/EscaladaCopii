from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import jwt
import pytest

pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from escalada.security import admin_license


@pytest.fixture(autouse=True)
def reset_admin_license_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("ESCALADA_SECRETS_DIR", str(tmp_path))
    monkeypatch.delenv("ADMIN_LICENSE_PUBLIC_KEY_PEM", raising=False)
    monkeypatch.delenv("ADMIN_LICENSE_PUBLIC_KEYS_PEM_BY_KID", raising=False)
    monkeypatch.setenv("ADMIN_LICENSE_DEFAULT_KID", "default")
    monkeypatch.setattr(admin_license, "_cached_result", None, raising=False)
    monkeypatch.setattr(admin_license, "_cached_at_monotonic", 0.0, raising=False)
    yield


def _generate_ed25519_key_pair() -> tuple[str, str]:
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


def _write_license_jwt(
    *,
    path: Path,
    private_pem: str,
    exp_ts: int,
    kid: str | None = None,
    iss: str = "escalada",
    aud: str = "escalada-admin",
    license_id: str | None = None,
) -> None:
    now_ts = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "iss": iss,
        "aud": aud,
        "iat": now_ts,
        "exp": exp_ts,
        "license_id": license_id or str(uuid4()),
    }
    headers = {"kid": kid} if kid else None
    token = jwt.encode(payload, private_pem, algorithm="EdDSA", headers=headers)
    path.write_text(token, encoding="utf-8")


def test_admin_license_missing_file_returns_not_found():
    status = admin_license.check_admin_license(force_refresh=True)
    assert status["valid"] is False
    assert status["reason"] == "not_found"


def test_admin_license_missing_default_key_returns_misconfigured(monkeypatch, tmp_path):
    private_pem, _public_pem = _generate_ed25519_key_pair()
    license_path = tmp_path / "admin_license.jwt"
    _write_license_jwt(
        path=license_path,
        private_pem=private_pem,
        exp_ts=int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        kid=None,
    )
    monkeypatch.setattr(admin_license, "PUBLIC_KEYS_PEM_BY_KID", {}, raising=False)
    monkeypatch.delenv("ADMIN_LICENSE_PUBLIC_KEY_PEM", raising=False)
    monkeypatch.delenv("ADMIN_LICENSE_PUBLIC_KEYS_PEM_BY_KID", raising=False)

    status = admin_license.check_admin_license(force_refresh=True)
    assert status["valid"] is False
    assert status["reason"] == "misconfigured"


def test_admin_license_invalid_signature(monkeypatch, tmp_path):
    private_pem_a, _public_pem_a = _generate_ed25519_key_pair()
    _private_pem_b, public_pem_b = _generate_ed25519_key_pair()
    monkeypatch.setattr(
        admin_license,
        "PUBLIC_KEYS_PEM_BY_KID",
        {"default": public_pem_b},
        raising=False,
    )

    license_path = tmp_path / "admin_license.jwt"
    _write_license_jwt(
        path=license_path,
        private_pem=private_pem_a,
        exp_ts=int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        kid="default",
    )
    status = admin_license.check_admin_license(force_refresh=True)
    assert status["valid"] is False
    assert status["reason"] == "invalid_signature"


def test_admin_license_valid_before_expiry(monkeypatch, tmp_path):
    private_pem, public_pem = _generate_ed25519_key_pair()
    monkeypatch.setattr(
        admin_license,
        "PUBLIC_KEYS_PEM_BY_KID",
        {"default": public_pem},
        raising=False,
    )

    now = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
    exp = int((now + timedelta(hours=2)).timestamp())
    license_id = str(uuid4())
    _write_license_jwt(
        path=tmp_path / "admin_license.jwt",
        private_pem=private_pem,
        exp_ts=exp,
        kid="default",
        license_id=license_id,
    )

    status = admin_license.check_admin_license(force_refresh=True, now_utc=now)
    assert status["valid"] is True
    assert status["in_grace"] is False
    assert status["reason"] == "ok"
    assert status["license_id"] == license_id


def test_admin_license_grace_window(monkeypatch, tmp_path):
    private_pem, public_pem = _generate_ed25519_key_pair()
    monkeypatch.setattr(
        admin_license,
        "PUBLIC_KEYS_PEM_BY_KID",
        {"default": public_pem},
        raising=False,
    )

    base = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
    exp = int(base.timestamp())
    _write_license_jwt(
        path=tmp_path / "admin_license.jwt",
        private_pem=private_pem,
        exp_ts=exp,
        kid="default",
    )

    status = admin_license.check_admin_license(
        force_refresh=True,
        now_utc=base + timedelta(hours=6),
    )
    assert status["valid"] is True
    assert status["in_grace"] is True
    assert status["reason"] == "grace"


def test_admin_license_expired_after_grace(monkeypatch, tmp_path):
    private_pem, public_pem = _generate_ed25519_key_pair()
    monkeypatch.setattr(
        admin_license,
        "PUBLIC_KEYS_PEM_BY_KID",
        {"default": public_pem},
        raising=False,
    )

    base = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
    exp = int(base.timestamp())
    _write_license_jwt(
        path=tmp_path / "admin_license.jwt",
        private_pem=private_pem,
        exp_ts=exp,
        kid="default",
    )

    status = admin_license.check_admin_license(
        force_refresh=True,
        now_utc=base + timedelta(hours=25),
    )
    assert status["valid"] is False
    assert status["in_grace"] is False
    assert status["reason"] == "expired"
