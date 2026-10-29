"""Bedrock Nova Pro adapter for validated extraction only; no financial tools."""

import asyncio
from contextlib import closing

import boto3
from botocore.config import Config

from app.agent.state import Extraction


def tool_schema():
    raw = Extraction.model_json_schema()

    def inline(node):
        if "$ref" in node:
            return inline(raw["$defs"][node["$ref"].split("/")[-1]])
        result = {
            key: value
            for key, value in node.items()
            if key in {"type", "enum", "required", "description"}
        }
        if "properties" in node:
            result["properties"] = {key: inline(value) for key, value in node["properties"].items()}
        if "items" in node:
            result["items"] = inline(node["items"])
        return result

    return {
        key: value
        for key, value in inline(raw).items()
        if key in {"type", "properties", "required"}
    }


class NovaExtractor:
    def __init__(self, settings):
        self.settings = settings

    async def ainvoke(self, messages, config=None):
        return await asyncio.to_thread(self.invoke, messages)

    def invoke(self, messages):
        settings = self.settings
        credentials = {
            name: value.get_secret_value()
            for name, value in {
                "aws_access_key_id": settings.aws_access_key_id,
                "aws_secret_access_key": settings.aws_secret_access_key,
                "aws_session_token": settings.aws_session_token,
            }.items()
            if value is not None
        }
        # Absent explicit keys, boto3 retains its standard IAM role/profile credential chain.
        with closing(
            boto3.client(
                "bedrock-runtime",
                region_name=settings.aws_region,
                config=Config(
                    connect_timeout=2,
                    read_timeout=settings.bedrock_timeout_seconds,
                    retries={"total_max_attempts": 1},
                ),
                **credentials,
            )
        ) as client:
            response = client.converse(
                modelId=settings.bedrock_model_id,
                system=[{"text": messages[0].content}],
                messages=[{"role": "user", "content": [{"text": messages[1].content}]}],
                inferenceConfig={"temperature": 0, "maxTokens": 1600},
                toolConfig={
                    "tools": [
                        {
                            "toolSpec": {
                                "name": "extract_complaint",
                                "description": (
                                    "Classify the current rider request and extract claim scope "
                                    "or an educational topic. Only general non-account "
                                    "education may include help_answer."
                                ),
                                "inputSchema": {"json": tool_schema()},
                            }
                        }
                    ],
                    "toolChoice": {"tool": {"name": "extract_complaint"}},
                },
            )
        tools = [
            block["toolUse"]
            for block in response["output"]["message"]["content"]
            if "toolUse" in block
        ]
        if len(tools) != 1 or tools[0]["name"] != "extract_complaint":
            raise ValueError("Nova did not return the required extraction")
        # Ignore all free text/reasoning; only the validated tool payload enters the graph.
        return Extraction.model_validate(tools[0]["input"])
