#!/usr/bin/env python3
"""
Seeds local PostgreSQL with fixture data for E2E testing.
Run after docker-compose up -d.

Usage:
  python tests/fixtures/seed_local_db.py
"""
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USER", "qrate")
os.environ.setdefault("DB_PASSWORD", "localpassword")
os.environ.setdefault("DB_NAME", "menucrawler")

from sqlalchemy import text
from app.services.postgres import AsyncSessionLocal

FIXTURES_DIR = Path(__file__).parent
MENU_FILE = FIXTURES_DIR / "sample_menu.json"
GUESTS_FILE = FIXTURES_DIR / "sample_guests.json"

RESTAURANT_ID = "r0000000-0000-0000-0000-000000000001"


async def create_schema(db):
    """Create minimal schema for local testing if tables don't exist."""
    await db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await db.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            restaurant_id UUID REFERENCES restaurants(id),
            name VARCHAR(255) NOT NULL,
            description TEXT,
            price DECIMAL(10,2),
            food_tags JSONB DEFAULT '{}',
            embedding_vector vector(1536),
            margin_score DECIMAL(3,1) DEFAULT 5.0,
            upsell_pointers UUID[] DEFAULT '{}',
            cross_sell_pointers UUID[] DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS diner_profiles (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            allergens TEXT[] DEFAULT '{}',
            dietary_restrictions TEXT[] DEFAULT '{}',
            spice_preference INTEGER,
            favorite_cuisines TEXT[] DEFAULT '{}',
            preference_map JSONB DEFAULT '{}',
            context_history TEXT,
            anniversary_date DATE,
            birthday DATE,
            visit_context VARCHAR(50),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS event_menu_mappings (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            event_type VARCHAR(100) NOT NULL,
            restaurant_id UUID REFERENCES restaurants(id),
            menu_item_ids UUID[] NOT NULL DEFAULT '{}',
            active_from TIMESTAMP WITH TIME ZONE,
            active_until TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """))
    await db.commit()


async def seed_restaurant(db):
    await db.execute(text("""
        INSERT INTO restaurants (id, name)
        VALUES (:id, :name)
        ON CONFLICT (id) DO NOTHING
    """), {"id": RESTAURANT_ID, "name": "Test Restaurant"})
    await db.commit()


async def seed_menu_items(db):
    items = json.loads(MENU_FILE.read_text())
    for item in items:
        upsell = "{" + ",".join(item.get("upsell_pointers", [])) + "}"
        cross_sell = "{" + ",".join(item.get("cross_sell_pointers", [])) + "}"
        allergens_arr = "{" + ",".join(item.get("food_tags", {}).get("allergens", [])) + "}"

        await db.execute(text("""
            INSERT INTO menu_items
                (id, restaurant_id, name, description, price, food_tags,
                 margin_score, upsell_pointers, cross_sell_pointers)
            VALUES
                (:id, :restaurant_id, :name, :description, :price, :food_tags::jsonb,
                 :margin_score, :upsell_pointers::uuid[], :cross_sell_pointers::uuid[])
            ON CONFLICT (id) DO UPDATE SET
                food_tags = EXCLUDED.food_tags,
                margin_score = EXCLUDED.margin_score
        """), {
            "id": item["id"],
            "restaurant_id": item["restaurant_id"],
            "name": item["name"],
            "description": item.get("description", ""),
            "price": item.get("price"),
            "food_tags": json.dumps(item.get("food_tags", {})),
            "margin_score": item.get("margin_score", 5.0),
            "upsell_pointers": upsell,
            "cross_sell_pointers": cross_sell,
        })
    await db.commit()
    print(f"Seeded {len(items)} menu items")


async def seed_guest_profiles(db):
    guests = json.loads(GUESTS_FILE.read_text())
    today = date.today().isoformat()
    for g in guests:
        birthday = g.get("birthday")
        if birthday == "__TODAY__":
            birthday = today

        allergens = "{" + ",".join(g.get("allergens", [])) + "}"
        dietary = "{" + ",".join(g.get("dietary_restrictions", [])) + "}"
        cuisines = "{" + ",".join(g.get("favorite_cuisines", [])) + "}"

        await db.execute(text("""
            INSERT INTO diner_profiles
                (id, allergens, dietary_restrictions, spice_preference,
                 favorite_cuisines, preference_map, visit_context, birthday)
            VALUES
                (:id, :allergens, :dietary, :spice, :cuisines,
                 :pref_map::jsonb, :visit_context, :birthday::date)
            ON CONFLICT (id) DO NOTHING
        """), {
            "id": g["id"],
            "allergens": allergens,
            "dietary": dietary,
            "spice": g.get("spice_preference"),
            "cuisines": cuisines,
            "pref_map": json.dumps(g.get("preference_map", {})),
            "visit_context": g.get("visit_context"),
            "birthday": birthday,
        })
    await db.commit()
    print(f"Seeded {len(guests)} guest profiles")


async def main():
    print("Seeding local database...")
    async with AsyncSessionLocal() as db:
        await create_schema(db)
        await seed_restaurant(db)
        await seed_menu_items(db)
        await seed_guest_profiles(db)
    print("Done! Local database is ready.")


if __name__ == "__main__":
    asyncio.run(main())
