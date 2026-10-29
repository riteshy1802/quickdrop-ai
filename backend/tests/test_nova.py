from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent import llm, nova
from app.core.config import Settings


async def test_nova_converse_extracts_only_validated_tool_payload(monkeypatch):
    client = MagicMock(spec=["converse", "close"])
    client.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {"text": "private model reasoning"},
                    {
                        "toolUse": {
                            "name": "extract_complaint",
                            "input": {
                                "intent": "other",
                                "language": "en",
                                "claims": [],
                            },
                        }
                    },
                ]
            }
        }
    }
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr(nova.boto3, "client", constructor)
    settings = Settings(
        _env_file=None,
        llm_provider="amazon",
        aws_access_key_id="test-only",
        aws_secret_access_key="test-only",
    )
    value = await nova.NovaExtractor(settings).ainvoke(
        [
            SystemMessage(content="test instructions"),
            HumanMessage(content="hello"),
        ]
    )
    assert value.intent == "other" and value.language == "en"
    client.close.assert_called_once()
    assert constructor.call_args.kwargs["region_name"] == "us-east-1"
    request = client.converse.call_args.kwargs
    assert request["modelId"] == "us.amazon.nova-pro-v1:0"
    assert request["toolConfig"]["toolChoice"] == {"tool": {"name": "extract_complaint"}}
    schema = request["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"]
    assert set(schema) == {"type", "properties", "required"}
    assert "$ref" not in str(schema)


def test_amazon_selection_does_not_require_groq_credentials(monkeypatch):
    monkeypatch.setattr(
        llm, "get_settings", lambda: Settings(_env_file=None, llm_provider="amazon")
    )
    llm.get_extractor.cache_clear()
    try:
        assert isinstance(llm.get_extractor(), nova.NovaExtractor)
    finally:
        llm.get_extractor.cache_clear()


async def test_nova_rejects_free_text_in_place_of_extraction(monkeypatch):
    client = MagicMock(spec=["converse", "close"])
    client.converse.return_value = {"output": {"message": {"content": [{"text": "untrusted"}]}}}
    monkeypatch.setattr(nova.boto3, "client", lambda *args, **kwargs: client)
    with pytest.raises(ValueError, match="required extraction"):
        await nova.NovaExtractor(Settings(_env_file=None)).ainvoke(
            [
                SystemMessage(content="test"),
                HumanMessage(content="test"),
            ]
        )
