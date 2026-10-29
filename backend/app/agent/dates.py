"""Resolve only explicit rider date tokens against the vendor timestamp in IST."""

import calendar
import re
from datetime import date, datetime, timedelta

from app.repositories.trips import IST

MONTHS = {name.lower(): index for index, name in enumerate(calendar.month_abbr) if name}
MONTHS.update({name.lower(): index for index, name in enumerate(calendar.month_name) if name})
MONTHS["sept"] = 9
MONTHS.update({"सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10})
DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def resolve_date(token: str, received_at: datetime) -> date:
    current = received_at.astimezone(IST).date()
    text = token.lower().strip().translate(DIGITS)
    if text in {"kal", "yesterday", "कल"}:
        return current - timedelta(days=1)
    if text in {"parso", "parson", "day before yesterday", "परसों"}:
        return current - timedelta(days=2)
    if text in {"today", "aaj", "आज"}:
        return current
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return date.fromisoformat(text)
    cleaned = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", text)
    cleaned = re.sub(r"\b(tarikh|tareekh|ko|on|of)\b", " ", cleaned).strip()
    parts = re.findall(r"[a-z]+|[\u0900-\u097f]+|\d+", cleaned)
    numbers = [int(part) for part in parts if part.isdigit()]
    if not numbers or len(numbers) > 2:
        raise ValueError("Provide an explicit date")
    day = numbers[0]
    month = next((MONTHS[part] for part in parts if part in MONTHS), current.month)
    year = numbers[1] if len(numbers) == 2 and numbers[1] >= 1900 else current.year
    if (
        month == current.month
        and day > current.day
        and not any(part in MONTHS for part in parts)
        and len(numbers) == 1
    ):
        prior = current.replace(day=1) - timedelta(days=1)
        return date(prior.year, prior.month, day)
    value = date(year, month, day)
    if value > current and len(numbers) == 1 and not any(part in MONTHS for part in parts):
        if month != current.month:
            value = date(year - 1, month, day)
        else:
            first = current.replace(day=1) - timedelta(days=1)
            value = date(first.year, first.month, day)
    return value


def grounded(token: str, text: str) -> bool:
    token, text = token.translate(DIGITS).strip(), text.translate(DIGITS)
    return (
        bool(token)
        and re.search(r"(?<![\w])" + re.escape(token) + r"(?![\w])", text, re.I) is not None
    )


def matches_trip_date(token: str, service_date: date, resolved: date) -> bool:
    """A bare day constrains an identified trip's day, not an invented month.

    Relative or explicit dates still match the full resolved date. This never changes
    received_at or seven-day eligibility; the financial engine checks those separately.
    """
    text = token.lower().strip().translate(DIGITS)
    bare = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?(?:\s+(?:tarikh|tareekh|ko|wala))?", text)
    return service_date.day == int(bare[1]) if bare else service_date == resolved


def literal_dates(text: str) -> list[str]:
    """Copy explicit supported date phrases for the narrow complaint-routing guard."""
    months = "|".join(re.escape(month) for month in sorted(MONTHS, key=len, reverse=True))
    # Capture impossible supplied days too, so validation can explain them explicitly.
    day = r"\d{1,4}(?:st|nd|rd|th)?"
    pattern = (
        rf"(?<!\w)(?:\d{{4}}-\d{{2}}-\d{{2}}|"
        rf"{day}\s+(?:{months})(?:\s+\d{{4}})?|"
        rf"(?:{months})\s+{day}(?:\s+\d{{4}})?|"
        rf"{day}\s+(?:tarikh|tareekh|ko|wala)|"
        r"day before yesterday|yesterday|today|parso|parson|kal|aaj|कल|आज|परसों)(?!\w)"
    )
    return list(dict.fromkeys(match[0] for match in re.finditer(pattern, text, re.I)))
