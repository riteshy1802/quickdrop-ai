"""Explicit local historical replay in disposable PostgreSQL with a mock provider."""

import argparse
import subprocess
import sys

from app.core.config import BACKEND_DIR, get_settings


def require_local_test_mode(settings, enabled):
    if not enabled:
        raise ValueError("Historical replay requires --local-test-mode")
    if settings.app_env != "development" or settings.sqlalchemy_url.host not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("Historical replay is restricted to development with local PostgreSQL")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-test-mode", action="store_true")
    args = parser.parse_args()
    try:
        require_local_test_mode(get_settings(), args.local_test_mode)
    except ValueError as exc:
        parser.error(str(exc))
    print(
        "Replaying original received_at timestamps in a fresh disposable database. "
        "Groq extraction is labelled; PaySwift is mocked. No live payments are issued.",
        flush=True,
    )
    return subprocess.call(
        [sys.executable, "-m", "pytest", "-q", "tests/test_agent_scenarios.py"],
        cwd=BACKEND_DIR,
    )


if __name__ == "__main__":
    raise SystemExit(main())
