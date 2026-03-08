"""
AWS Bedrock client — Claude Sonnet for reasoning/pitches, Titan Embeddings v2 for vectors.
Mirrors the existing qrate-core Bedrock pattern.
"""
import json
import boto3
from botocore.config import Config
from tenacity import retry, stop_after_attempt, wait_exponential
from app.utils.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _build_bedrock_client():
    kwargs = dict(
        service_name="bedrock-runtime",
        region_name=settings.aws_region,
        config=Config(retries={"max_attempts": 3, "mode": "adaptive"}),
    )
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    if settings.bedrock_endpoint:
        kwargs["endpoint_url"] = settings.bedrock_endpoint
    return boto3.client(**kwargs)


_bedrock_client = None


def get_bedrock_client():
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = _build_bedrock_client()
    return _bedrock_client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def invoke_claude(system_prompt: str, user_message: str, max_tokens: int = 1024) -> str:
    """
    Invoke Claude via Bedrock Messages API.
    Returns the text content of the first message block.
    """
    client = get_bedrock_client()
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    })
    response = client.invoke_model(
        modelId=settings.bedrock_model_id,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    logger.debug(
        "Claude invoked",
        input_tokens=result.get("usage", {}).get("input_tokens"),
        output_tokens=result.get("usage", {}).get("output_tokens"),
    )
    return result["content"][0]["text"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def generate_embedding(text: str) -> list[float]:
    """
    Generate a 1536-dim embedding via Amazon Titan Embeddings v2.
    Uses the same Bedrock client — no additional credentials needed.
    """
    client = get_bedrock_client()
    body = json.dumps({"inputText": text, "dimensions": 1536, "normalize": True})
    response = client.invoke_model(
        modelId=settings.titan_embedding_model_id,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    return result["embedding"]
