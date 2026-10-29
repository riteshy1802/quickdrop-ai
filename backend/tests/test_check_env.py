"""Configuration validation must never disclose values or open dotenv files."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.scripts.check_env import check_environment, main


def configure(monkeypatch):
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    for name, value in {
        "POSTGRES_PASSWORD": "disposable-test-password",
        "OPS_ADMIN_EMAIL": "operator@example.invalid",
        "OPS_ADMIN_PASSWORD": "disposable-admin-password",
        "DEMO_SESSION_SECRET": "x" * 40,
        "LLM_PROVIDER": "groq",
        "GROQ_API_KEY": "disposable-provider-key",
    }.items():
        monkeypatch.setenv(name, value)


def test_presence_only_and_optional_fields(monkeypatch, capsys):
    configure(monkeypatch)
    statuses, failed = check_environment()
    assert not failed
    assert statuses["AWS_SESSION_TOKEN"] == "Missing"
    assert statuses["GROQ_API_KEY"] == "Configured"
    assert main() == 0
    output = capsys.readouterr().out
    assert "disposable" not in output and "example.invalid" not in output
    assert all(line.split(": ")[1] in {"Configured", "Missing"} for line in output.splitlines())


def test_invalid_and_missing_values_remain_redacted(monkeypatch, capsys):
    configure(monkeypatch)
    monkeypatch.setenv("POSTGRES_PORT", "secret-invalid-port")
    monkeypatch.delenv("GROQ_API_KEY")
    assert main() == 1
    output = capsys.readouterr().out
    assert "POSTGRES_PORT: Invalid format" in output
    assert "GROQ_API_KEY: Missing" in output
    assert "secret-invalid-port" not in output


def test_placeholder_credentials_and_production_clock_rejected(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("POSTGRES_PASSWORD", "replace_with_a_local_password")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_REFERENCE_TIME", "2026-09-23T12:30:00+05:30")
    statuses, failed = check_environment()
    assert failed
    assert statuses["POSTGRES_PASSWORD"] == "Invalid format"
    assert statuses["APP_REFERENCE_TIME"] == "Invalid format"


def test_settings_validation_exception_hides_input(monkeypatch):
    configure(monkeypatch)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, postgres_port="private-input-must-not-leak")
    assert "private-input-must-not-leak" not in str(error.value)


def test_invalid_connection_urls_are_redacted(monkeypatch, capsys):
    configure(monkeypatch)
    monkeypatch.setenv("REDIS_URL", "redis://private-user:private-password@host:invalid")
    monkeypatch.setenv("PAYSWIFT_BASE_URL", "not-a-url-with-private-input")
    monkeypatch.setenv("DATABASE_URL", "not-a-postgres-url-with-private-input")
    assert main() == 1
    output = capsys.readouterr().out
    for name in ("REDIS_URL", "PAYSWIFT_BASE_URL", "DATABASE_URL"):
        assert f"{name}: Invalid format" in output
    assert "private-" not in output


def test_valid_database_password_has_no_invented_prefix_restriction(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("POSTGRES_PASSWORD", "your_valid_disposable_database_password")
    statuses, failed = check_environment()
    assert not failed
    assert statuses["POSTGRES_PASSWORD"] == "Configured"
