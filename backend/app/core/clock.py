"""Business reference time only; operational timestamps always use the system clock."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings

IST = ZoneInfo("Asia/Kolkata")


def reference_time(*, received_at=None, interactive_demo=False):
    """Explicit evaluator event times win; only authenticated demo submissions opt in."""
    settings = get_settings()
    if interactive_demo and settings.app_reference_time is not None:
        if settings.app_env != "development":
            raise ValueError("Historical demo clock is disabled outside development")
        value = settings.app_reference_time
    else:
        value = received_at or datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Business reference time must be timezone-aware")
    return value.astimezone(IST)


def claim_time(request):
    """Use the claim's durable demo snapshot, otherwise its original evaluator event."""
    if (
        request.reference_time is not None
        and request.reference_time != request.received_at
        and get_settings().app_env != "development"
    ):
        raise ValueError("Demo claim reference times are disabled outside development")
    return reference_time(received_at=request.reference_time or request.received_at)
