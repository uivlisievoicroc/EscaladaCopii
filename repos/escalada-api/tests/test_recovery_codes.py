from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from escalada.security import recovery_codes


@pytest.fixture(autouse=True)
def configure_recovery_store(monkeypatch, tmp_path):
    monkeypatch.setenv("ESCALADA_SECRETS_DIR", str(tmp_path))
    recovery_codes.reset_runtime_state()
    yield
    recovery_codes.reset_runtime_state()


def _build_store(raw_codes: list[str], now_utc: datetime) -> dict:
    return {
        "version": 1,
        "created_at": now_utc.isoformat(),
        "override_ttl_hours": 24,
        "codes": [
            {
                "code_id": f"rc_{index:03d}",
                "hash": recovery_codes.hash_recovery_code(code),
                "used_at": None,
            }
            for index, code in enumerate(raw_codes, start=1)
        ],
        "override": {
            "active_until": None,
            "activated_at": None,
            "activated_by_ip": None,
        },
    }


def test_consume_valid_code_marks_used_and_activates_override():
    now = datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc)
    store = _build_store(["ABCD-EFGH-JKLM-NPQR"], now)
    recovery_codes.save_recovery_store_atomic(store)

    result = recovery_codes.consume_recovery_code(
        "abcd efgh-jklm npqr",
        "10.0.0.5",
        now_utc=now,
    )

    assert result["ok"] is True
    assert result["remaining"] == 0
    assert result["code_id"] == "rc_001"
    assert result["override_until"] == now + timedelta(hours=24)

    updated = recovery_codes.load_recovery_store()
    assert updated["codes"][0]["used_at"] == now.isoformat()
    assert (
        updated["override"]["active_until"] == (now + timedelta(hours=24)).isoformat()
    )
    assert updated["override"]["activated_at"] == now.isoformat()
    assert updated["override"]["activated_by_ip"] == "10.0.0.5"


def test_consume_same_code_twice_returns_invalid(monkeypatch):
    now = datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc)
    store = _build_store(["ABCD-EFGH-JKLM-NPQR"], now)
    recovery_codes.save_recovery_store_atomic(store)
    monkeypatch.setattr(recovery_codes.time, "sleep", lambda _: None)

    recovery_codes.consume_recovery_code("ABCD-EFGH-JKLM-NPQR", "10.0.0.6", now_utc=now)
    with pytest.raises(recovery_codes.RecoveryInvalidCodeError):
        recovery_codes.consume_recovery_code(
            "ABCD-EFGH-JKLM-NPQR",
            "10.0.0.6",
            now_utc=now + timedelta(hours=25),
        )


def test_override_active_returns_override_active_error():
    now = datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc)
    store = _build_store(["ABCD-EFGH-JKLM-NPQR"], now)
    expected_until = now + timedelta(hours=2)
    store["override"] = {
        "active_until": expected_until.isoformat(),
        "activated_at": now.isoformat(),
        "activated_by_ip": "127.0.0.1",
    }
    recovery_codes.save_recovery_store_atomic(store)

    with pytest.raises(recovery_codes.RecoveryOverrideActiveError) as exc:
        recovery_codes.consume_recovery_code(
            "ABCD-EFGH-JKLM-NPQR",
            "10.0.0.7",
            now_utc=now + timedelta(minutes=5),
        )

    assert exc.value.active_until == expected_until
    unchanged = recovery_codes.load_recovery_store()
    assert unchanged["codes"][0]["used_at"] is None


def test_override_expiry_after_ttl_is_not_active():
    now = datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc)
    store = _build_store(["ABCD-EFGH-JKLM-NPQR"], now)
    store["override"] = {
        "active_until": (now - timedelta(seconds=1)).isoformat(),
        "activated_at": (now - timedelta(hours=24)).isoformat(),
        "activated_by_ip": "127.0.0.1",
    }
    recovery_codes.save_recovery_store_atomic(store)

    assert recovery_codes.is_override_active(now_utc=now) is False
    assert recovery_codes.get_override_until(now_utc=now) is None


def test_rate_limit_returns_429_equivalent(monkeypatch):
    now = datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc)
    recovery_codes.save_recovery_store_atomic(
        _build_store(["WXYZ-WXYZ-WXYZ-WXYZ"], now)
    )
    monkeypatch.setattr(recovery_codes.time, "sleep", lambda _: None)

    for idx in range(5):
        with pytest.raises(recovery_codes.RecoveryInvalidCodeError):
            recovery_codes.consume_recovery_code(
                "NOPE-NOPE-NOPE-NOPE",
                "10.0.0.9",
                now_utc=now + timedelta(seconds=idx),
            )

    with pytest.raises(recovery_codes.RecoveryRateLimitError):
        recovery_codes.consume_recovery_code(
            "NOPE-NOPE-NOPE-NOPE",
            "10.0.0.9",
            now_utc=now + timedelta(seconds=6),
        )


def test_store_contains_only_hashes_no_plaintext():
    now = datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc)
    plain_code = "QWER-TYUI-OPAS-DFGH"
    recovery_codes.save_recovery_store_atomic(_build_store([plain_code], now))

    raw_store_text = recovery_codes.get_recovery_store_path().read_text(
        encoding="utf-8"
    )
    assert plain_code not in raw_store_text
    assert "hash" in raw_store_text


def test_backoff_increases_without_real_sleep(monkeypatch):
    now = datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc)
    recovery_codes.save_recovery_store_atomic(
        _build_store(["ZXCV-BNMK-LJHG-FDSA"], now)
    )

    calls: list[float] = []
    monkeypatch.setattr(
        recovery_codes.time, "sleep", lambda value: calls.append(float(value))
    )

    for idx in range(4):
        with pytest.raises(recovery_codes.RecoveryInvalidCodeError):
            recovery_codes.consume_recovery_code(
                "WRNG-WRNG-WRNG-WRNG",
                "10.0.0.10",
                now_utc=now + timedelta(seconds=idx),
            )

    assert calls == sorted(calls)
    assert calls[0] == 0.25
    assert calls[-1] == 2.0
