import escalada.auth.deps as auth_deps
import escalada.main as main_module


def test_main_secret_helpers_detect_weak_values():
    assert main_module._is_weak_jwt_secret(None) is True
    assert main_module._is_weak_jwt_secret("dev-secret-change-me") is True
    assert main_module._is_weak_jwt_secret("strong-secret") is False


def test_trusted_admin_ip_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("ADMIN_TRUSTED_IPS", raising=False)
    assert auth_deps.is_trusted_admin_ip("127.0.0.1") is True
    assert auth_deps.is_trusted_admin_ip("::1") is True
    assert auth_deps.is_trusted_admin_ip("localhost") is True
    assert auth_deps.is_trusted_admin_ip("10.10.10.10") is False


def test_trusted_admin_ip_uses_env_allowlist(monkeypatch):
    monkeypatch.setenv("ADMIN_TRUSTED_IPS", "10.0.0.1,testclient")
    assert auth_deps.is_trusted_admin_ip("testclient") is True
    assert auth_deps.is_trusted_admin_ip("10.0.0.1") is True
    assert auth_deps.is_trusted_admin_ip("127.0.0.1") is False
