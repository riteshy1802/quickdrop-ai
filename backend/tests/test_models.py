"""Database-free model, configuration and trace validation."""

from sqlalchemy import Float, UniqueConstraint, inspect
from sqlalchemy.orm import configure_mappers

from app.core.config import Settings
from app.models import AgentTrace, Base, Conversation, Dispute, OpsUser, Rider
from app.models.agent_trace import redact_trace_payload


def test_metadata_and_relationships():
    configure_mappers()
    assert set(Base.metadata.tables) == {
        "riders",
        "trips",
        "payout_lines",
        "ops_users",
        "ops_sessions",
        "ops_login_limits",
        "conversations",
        "messages",
        "disputes",
        "dispute_items",
        "payment_intents",
        "ops_queue",
        "agent_traces",
    }
    for table in Base.metadata.tables.values():
        assert not any(isinstance(column.type, Float) for column in table.columns)
        indexes = [tuple(c.name for c in index.columns) for index in table.indexes]
        indexes += [
            tuple(c.name for c in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        for fk in table.foreign_key_constraints:
            columns = tuple(c.name for c in fk.columns)
            assert any(index[: len(columns)] == columns for index in indexes), (table.name, columns)
            assert fk.ondelete == "RESTRICT"
    for model in (Rider, Conversation, Dispute, OpsUser):
        assert len(inspect(model).relationships) > 0


def test_settings_escape_password_and_hide_secrets(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None, postgres_password="p@ss/%:word")
    assert settings.sqlalchemy_url.password == "p@ss/%:word"
    assert settings.sqlalchemy_url.drivername == "postgresql+asyncpg"
    assert "p@ss" not in repr(settings)
    assert "p@ss" not in str(settings.sqlalchemy_url)


def test_trace_redaction():
    payload = {
        "trip": "T1",
        "nested": [{"Authorization": "secret", "password_hash": "hash"}],
        "chain_of_thought": "private",
        "output": "public decision",
    }
    result = redact_trace_payload(payload)
    assert result["nested"][0] == {"Authorization": "[REDACTED]", "password_hash": "[REDACTED]"}
    assert result["chain_of_thought"] == "[REDACTED]"
    assert result["output"] == "public decision"
    trace = AgentTrace(input=payload, output="Public result")
    assert trace.input == result and trace.output == "Public result"
