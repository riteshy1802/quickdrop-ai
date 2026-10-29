"""One async extraction call, validated output, no model-controlled financial actions."""

import asyncio
import json
import logging
from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langsmith import tracing_context

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import Extraction
from app.core.config import get_settings
from app.repositories.trips import IST

logger = logging.getLogger(__name__)
STRICT_JSON_MODELS = {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}


class ExtractionUnavailable(Exception):
    pass


@lru_cache
def get_extractor():
    settings = get_settings()
    if settings.llm_provider == "amazon":
        from app.agent.nova import NovaExtractor

        return NovaExtractor(settings)
    if settings.groq_api_key is None:
        raise ExtractionUnavailable("LLM is not configured")
    model = ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0,
        timeout=settings.groq_timeout_seconds,
        max_retries=0,
        max_tokens=1600,
    )
    if settings.groq_model in STRICT_JSON_MODELS:
        return model.with_structured_output(Extraction, method="json_schema", strict=True)
    return model.with_structured_output(Extraction, method="function_calling")


async def extract(*, text, received_at, history, context) -> Extraction:
    settings = get_settings()
    payload = {
        "text": text,
        "received_at_ist": received_at.astimezone(IST).isoformat(),
        "prior_context": context,
        "recent_messages": history[-12:],
    }
    try:
        with tracing_context(enabled=False):
            return await _invoke(payload, settings)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        diagnostic = safe_failure(exc)
        logger.warning("%s extraction failed (%s)", settings.llm_provider, diagnostic)
        raise ExtractionUnavailable(diagnostic) from None


def safe_failure(exc):
    """Keep machine-readable diagnostics, never provider messages or failed generations."""
    parts = [type(exc).__name__]
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        parts.append(f"http={status}")
    body = getattr(exc, "body", None)
    error = body.get("error", body) if isinstance(body, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    known_codes = {
        "tool_use_failed",
        "json_validate_failed",
        "invalid_request_error",
        "context_length_exceeded",
        "model_not_found",
        "rate_limit_exceeded",
        "invalid_api_key",
        "insufficient_quota",
        "content_policy_violation",
    }
    if isinstance(code, str) and code in known_codes:
        parts.append(f"code={code}")
    return " ".join(parts)


async def _invoke(payload, settings):
    timeout = (
        settings.bedrock_timeout_seconds
        if settings.llm_provider == "amazon"
        else settings.groq_timeout_seconds
    )
    async with asyncio.timeout(timeout):
        value = await get_extractor().ainvoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ],
            config={"callbacks": [], "tags": ["quickdrop-extraction"]},
        )
        return value if isinstance(value, Extraction) else Extraction.model_validate(value)
