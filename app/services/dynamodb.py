"""
DynamoDB session management — mirrors the AI Waiter pattern in qrate-core.
Table: recommendation-sessions-{env}
PK: session_id (string)
SK: restaurant_id (string)
TTL: 3600 seconds
"""
import json
import time
import boto3
from botocore.config import Config
from app.utils.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

SESSION_TTL_SECONDS = 3600


def _build_dynamodb_client():
    kwargs = dict(
        service_name="dynamodb",
        region_name=settings.aws_region,
        config=Config(retries={"max_attempts": 3}),
    )
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    if settings.dynamodb_endpoint:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint
    return boto3.client(**kwargs)


_dynamo_client = None


def get_dynamo_client():
    global _dynamo_client
    if _dynamo_client is None:
        _dynamo_client = _build_dynamodb_client()
    return _dynamo_client


def get_session(session_id: str, restaurant_id: str) -> dict | None:
    client = get_dynamo_client()
    try:
        response = client.get_item(
            TableName=settings.dynamodb_sessions_table,
            Key={
                "session_id": {"S": session_id},
                "restaurant_id": {"S": restaurant_id},
            },
        )
        item = response.get("Item")
        if not item:
            return None
        return {
            "session_id": item["session_id"]["S"],
            "restaurant_id": item["restaurant_id"]["S"],
            "guest_id": item.get("guest_id", {}).get("S"),
            "pipeline_results": json.loads(item.get("pipeline_results", {}).get("S", "{}")),
            "accepted_items": json.loads(item.get("accepted_items", {}).get("S", "[]")),
            "cross_sell_state": json.loads(item.get("cross_sell_state", {}).get("S", "{}")),
        }
    except Exception as exc:
        logger.error("DynamoDB get_session failed", error=str(exc), session_id=session_id)
        return None


def put_session(
    session_id: str,
    restaurant_id: str,
    guest_id: str | None,
    pipeline_results: dict,
    accepted_items: list,
    cross_sell_state: dict,
) -> None:
    client = get_dynamo_client()
    ttl = int(time.time()) + SESSION_TTL_SECONDS
    try:
        client.put_item(
            TableName=settings.dynamodb_sessions_table,
            Item={
                "session_id": {"S": session_id},
                "restaurant_id": {"S": restaurant_id},
                "guest_id": {"S": guest_id or "anonymous"},
                "pipeline_results": {"S": json.dumps(pipeline_results)},
                "accepted_items": {"S": json.dumps(accepted_items)},
                "cross_sell_state": {"S": json.dumps(cross_sell_state)},
                "ttl": {"N": str(ttl)},
            },
        )
    except Exception as exc:
        logger.error("DynamoDB put_session failed", error=str(exc), session_id=session_id)


def ensure_table_exists() -> None:
    """Create the sessions table if it doesn't exist (local dev / CI only)."""
    client = get_dynamo_client()
    try:
        client.describe_table(TableName=settings.dynamodb_sessions_table)
    except client.exceptions.ResourceNotFoundException:
        logger.info("Creating DynamoDB table", table=settings.dynamodb_sessions_table)
        client.create_table(
            TableName=settings.dynamodb_sessions_table,
            KeySchema=[
                {"AttributeName": "session_id", "KeyType": "HASH"},
                {"AttributeName": "restaurant_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
                {"AttributeName": "restaurant_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        # Enable TTL
        client.update_time_to_live(
            TableName=settings.dynamodb_sessions_table,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
        )
        logger.info("DynamoDB table created", table=settings.dynamodb_sessions_table)
