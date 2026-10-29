"""Validate runtime configuration without opening dotenv files or revealing values.

Run through Compose, which supplies the environment. Missing optional settings are
reported but do not fail the check. No application connection is opened.
"""

import os
from collections.abc import Mapping
from urllib.parse import urlsplit

from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import Settings


def check_environment() -> tuple[Mapping[str, str], bool]:
    names = {field.upper() for field in Settings.model_fields}
    statuses = {
        name: "Configured" if os.environ.get(name, "").strip() else "Missing"
        for name in sorted(names)
    }
    required = {"OPS_ADMIN_EMAIL", "OPS_ADMIN_PASSWORD", "DEMO_SESSION_SECRET"}
    if statuses["DATABASE_URL"] != "Configured":
        required.update({"POSTGRES_PASSWORD"})
    provider = os.environ.get("LLM_PROVIDER", "groq")
    required.update(
        {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"} if provider == "amazon" else {"GROQ_API_KEY"}
    )
    try:
        # Explicitly disable dotenv reads. Compose supplies runtime variables.
        settings = Settings(_env_file=None)
    except ValidationError as exc:
        for error in exc.errors(include_input=False, include_context=False):
            name = str(error["loc"][0]).upper() if error["loc"] else "APP_REFERENCE_TIME"
            if name in statuses:
                statuses[name] = "Invalid format"
    else:
        for name, value, schemes in (
            ("REDIS_URL", settings.redis_url.get_secret_value(), {"redis", "rediss"}),
            ("PAYSWIFT_BASE_URL", settings.payswift_base_url, {"http", "https"}),
        ):
            try:
                url = urlsplit(value)
                if url.scheme not in schemes or not url.hostname:
                    raise ValueError
                _ = url.port
            except Exception:
                statuses[name] = "Invalid format"
        if settings.ops_admin_email and (
            "@" not in settings.ops_admin_email or len(settings.ops_admin_email) > 320
        ):
            statuses["OPS_ADMIN_EMAIL"] = "Invalid format"
        if settings.ops_admin_password and not (
            12 <= len(settings.ops_admin_password.get_secret_value()) <= 1024
        ):
            statuses["OPS_ADMIN_PASSWORD"] = "Invalid format"
        if settings.database_url:
            try:
                url = make_url(settings.database_url.get_secret_value())
                if url.drivername not in {"postgres", "postgresql", "postgresql+asyncpg"}:
                    raise ValueError
                if not url.host or not url.database:
                    raise ValueError
                _ = url.port
            except Exception:
                statuses["DATABASE_URL"] = "Invalid format"
    # Reject the exact public example, without inventing password-format rules.
    if os.environ.get("POSTGRES_PASSWORD") == "replace_with_a_local_password":
        statuses["POSTGRES_PASSWORD"] = "Invalid format"
    failed = any(value == "Invalid format" for value in statuses.values()) or any(
        statuses[name] != "Configured" for name in required
    )
    return statuses, failed


def main() -> int:
    try:
        statuses, failed = check_environment()
    except Exception:
        # Never print an exception, settings object, input or traceback.
        print("ENVIRONMENT: Invalid format")
        return 1
    for name, status in statuses.items():
        print(f"{name}: {status}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
