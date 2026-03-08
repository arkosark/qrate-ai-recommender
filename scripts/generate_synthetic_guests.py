#!/usr/bin/env python3
"""
Generate synthetic guest personas for load/safety testing.
Creates N diner_profiles rows with randomized allergens, dietary restrictions,
preference maps, and visit contexts.

Usage:
  python scripts/generate_synthetic_guests.py --count 5000
  python scripts/generate_synthetic_guests.py --count 100 --local
"""
import asyncio
import argparse
import sys
import os
import random
import json
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.services.postgres import AsyncSessionLocal
from app.utils.logging import get_logger, configure_logging

configure_logging("INFO")
logger = get_logger("generate_synthetic_guests")

ALLERGEN_POOL = ["nuts", "dairy", "gluten", "shellfish", "eggs", "soy", "fish", "sesame"]
DIETARY_POOL = ["vegetarian", "vegan", "halal", "kosher", "gluten_free"]
CUISINE_POOL = ["mexican", "italian", "japanese", "indian", "american", "thai", "mediterranean"]
TEXTURE_POOL = ["crunchy", "creamy", "light", "hearty", "crispy", "tender"]
FLAVOR_POOL = ["spicy", "citrus", "umami", "sweet", "savory", "smoky", "tangy"]
VISIT_CONTEXTS = ["Date Night", "Pre-Game", "Business Lunch", "Recovery", "Casual", "Celebration"]
DRINK_PREFS = ["margarita", "beer", "wine", "cocktail", "none", "water", "soda"]


def make_guest() -> dict:
    allergens = random.sample(ALLERGEN_POOL, random.randint(0, 3))
    dietary = random.sample(DIETARY_POOL, random.randint(0, 2))
    cuisines = random.sample(CUISINE_POOL, random.randint(1, 3))

    preference_map = {
        "spice_level": random.randint(1, 5),
        "likes_wine": random.choice([True, False]),
        "likes_beer": random.choice([True, False]),
        "texture_prefs": random.sample(TEXTURE_POOL, random.randint(1, 3)),
        "flavor_prefs": random.sample(FLAVOR_POOL, random.randint(1, 3)),
        "drink_preference": random.choice(DRINK_PREFS),
    }

    today = date.today()
    birthday = today - timedelta(days=random.randint(7000, 25000))
    # ~1% chance birthday is today (for birthday test scenario coverage)
    if random.random() < 0.01:
        birthday = today.replace(year=birthday.year)

    return {
        "id": str(uuid.uuid4()),
        "allergens": allergens,
        "dietary_restrictions": dietary,
        "spice_preference": preference_map["spice_level"],
        "favorite_cuisines": cuisines,
        "preference_map": json.dumps(preference_map),
        "visit_context": random.choice(VISIT_CONTEXTS),
        "birthday": birthday.isoformat(),
    }


async def insert_guests(guests: list[dict]) -> int:
    inserted = 0
    async with AsyncSessionLocal() as db:
        for g in guests:
            try:
                await db.execute(
                    text(
                        """
                        INSERT INTO diner_profiles
                            (id, allergens, dietary_restrictions, spice_preference,
                             favorite_cuisines, preference_map, visit_context, birthday)
                        VALUES
                            (:id, :allergens, :dietary_restrictions, :spice_preference,
                             :favorite_cuisines, :preference_map::jsonb,
                             :visit_context, :birthday::date)
                        ON CONFLICT (id) DO NOTHING
                        """
                    ),
                    {
                        **g,
                        "allergens": "{" + ",".join(g["allergens"]) + "}",
                        "dietary_restrictions": "{" + ",".join(g["dietary_restrictions"]) + "}",
                        "favorite_cuisines": "{" + ",".join(g["favorite_cuisines"]) + "}",
                    },
                )
                inserted += 1
            except Exception as exc:
                logger.error("Insert failed", guest_id=g["id"], error=str(exc))
        await db.commit()
    return inserted


async def main(args: argparse.Namespace) -> None:
    if args.local:
        os.environ.setdefault("DB_HOST", "localhost")
        os.environ.setdefault("DB_USER", "qrate")
        os.environ.setdefault("DB_PASSWORD", "localpassword")
        os.environ.setdefault("DB_NAME", "menucrawler")

    logger.info("Generating synthetic guests", count=args.count)
    guests = [make_guest() for _ in range(args.count)]

    # Write to JSON file for fixture reuse
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests", "fixtures", "synthetic_guests.json"
    )
    with open(output_path, "w") as f:
        json.dump(guests, f, indent=2)
    logger.info("Wrote guests to fixture file", path=output_path)

    if args.insert:
        count = await insert_guests(guests)
        logger.info("Inserted guests into DB", count=count)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic guest personas")
    parser.add_argument("--count", type=int, default=5000, help="Number of guests to generate")
    parser.add_argument("--local", action="store_true", help="Use local dev settings")
    parser.add_argument("--insert", action="store_true", help="Insert into database")
    args = parser.parse_args()
    asyncio.run(main(args))
