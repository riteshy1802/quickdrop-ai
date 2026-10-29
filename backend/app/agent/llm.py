"""One async extraction call, validated output, no model-controlled financial actions."""

import asyncio
import json
from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langsmith import tracing_context

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import Extraction
from app.core.config import get_settings
from app.repositories.trips import IST


class ExtractionUnavailable(Exception):
    pass


@lru_cache
def get_extractor():
    settings = get_settings()
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
        raise ExtractionUnavailable(type(exc).__name__) from None


async def _invoke(payload, settings):
    async with asyncio.timeout(settings.groq_timeout_seconds):
        value = await get_extractor().ainvoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ],
            config={"callbacks": [], "tags": ["quickdrop-extraction"]},
        )
        return value if isinstance(value, Extraction) else Extraction.model_validate(value)
