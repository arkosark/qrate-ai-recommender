#!/usr/bin/env python3
"""
Batch embedding generator — generates Titan embeddings for all menu items
in a restaurant that don't have one yet.

Usage:
  python scripts/generate_embeddings.py --restaurant-id <uuid>
  python scripts/generate_embeddings.py --local --restaurant-id test-restaurant-1
  python scripts/generate_embeddings.py --all-restaurants
"""
import asyncio
import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.services.postgres import AsyncSessionLocal
from app.services.embeddings import embed_menu_item, get_items_missing_embeddings
from app.utils.logging import get_logger, configure_logging

configure_logging("INFO")
logger = get_logger("generate_embeddings")


async def embed_restaurant(restaurant_id: str, batch_size: int = 100) -> int:
    """Embed all unembedded items for a restaurant. Returns count embedded."""
    from uuid import UUID
    rid = UUID(restaurant_id)
    total_embedded = 0

    async with AsyncSessionLocal() as db:
        while True:
            items = await get_items_missing_embeddings(db, rid, limit=batch_size)
            if not items:
                break
            logger.info(
                "Processing batch",
                restaurant_id=restaurant_id,
                batch_size=len(items),
            )
            for item in items:
                try:
                    await embed_menu_item(
                        db,
                        item_id=item["id"],
                        name=item["name"],
                        description=item.get("description", ""),
                        food_tags=item.get("food_tags", {}),
                    )
                    total_embedded += 1
                    if total_embedded % 10 == 0:
                        logger.info("Progress", embedded=total_embedded)
                except Exception as exc:
                    logger.error("Failed to embed item", item_id=str(item["id"]), error=str(exc))

    return total_embedded


async def get_all_restaurant_ids() -> list[str]:
    async with AsyncSessionLocal() as db:
        rows = await db.execute(text("SELECT id FROM restaurants"))
        return [str(row.id) for row in rows.fetchall()]


async def main(args: argparse.Namespace) -> None:
    if args.local:
        os.environ.setdefault("DB_HOST", "localhost")
        os.environ.setdefault("DB_USER", "qrate")
        os.environ.setdefault("DB_PASSWORD", "localpassword")
        os.environ.setdefault("DB_NAME", "menucrawler")
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
        os.environ.setdefault("BEDROCK_ENDPOINT", "http://localhost:8080")

    if args.all_restaurants:
        restaurant_ids = await get_all_restaurant_ids()
        logger.info("Embedding all restaurants", count=len(restaurant_ids))
    elif args.restaurant_id:
        restaurant_ids = [args.restaurant_id]
    else:
        logger.error("Must provide --restaurant-id or --all-restaurants")
        sys.exit(1)

    total = 0
    for rid in restaurant_ids:
        logger.info("Processing restaurant", restaurant_id=rid)
        count = await embed_restaurant(rid, batch_size=args.batch_size)
        logger.info("Restaurant complete", restaurant_id=rid, embedded=count)
        total += count

    logger.info("All done", total_embedded=total)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Titan embeddings for menu items")
    parser.add_argument("--restaurant-id", help="UUID of restaurant to embed")
    parser.add_argument("--all-restaurants", action="store_true", help="Embed all restaurants")
    parser.add_argument("--local", action="store_true", help="Use local dev settings")
    parser.add_argument("--batch-size", type=int, default=100, help="Items per batch")
    args = parser.parse_args()
    asyncio.run(main(args))
