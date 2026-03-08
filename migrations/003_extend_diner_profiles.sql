-- Migration 003: Extend diner_profiles with recommender signals
-- Corresponds to qrate-core migration 020_extend_diner_profiles.sql
-- Note: dietary_restrictions, allergens, spice_preference, favorite_cuisines already exist

ALTER TABLE diner_profiles
    ADD COLUMN IF NOT EXISTS preference_map JSONB DEFAULT '{}';
    -- e.g. {"spice_level": 4, "likes_wine": true, "texture_prefs": ["crunchy"],
    --        "flavor_prefs": ["citrus"], "drink_preference": "margarita"}

ALTER TABLE diner_profiles
    ADD COLUMN IF NOT EXISTS context_history TEXT;
    -- Running narrative of past visits and preferences for Claude context window

ALTER TABLE diner_profiles
    ADD COLUMN IF NOT EXISTS anniversary_date DATE;

-- Note: birthday already exists as dob in existing schema; adding alias column
-- if dob doesn't exist, add birthday directly
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='diner_profiles' AND column_name='birthday'
    ) THEN
        ALTER TABLE diner_profiles ADD COLUMN birthday DATE;
    END IF;
END$$;

ALTER TABLE diner_profiles
    ADD COLUMN IF NOT EXISTS visit_context VARCHAR(50);
    -- "Date Night", "Pre-Game", "Business Lunch", "Recovery", "Casual"

COMMENT ON COLUMN diner_profiles.preference_map IS
    'Flexible JSONB preference signals for AI recommender: spice, textures, flavors, drinks';
COMMENT ON COLUMN diner_profiles.context_history IS
    'Free-text history injected into Claude context window for personalization';
COMMENT ON COLUMN diner_profiles.visit_context IS
    'Current visit occasion: Date Night, Pre-Game, Business Lunch, Recovery, Casual';
