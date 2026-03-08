-- Migration 004: Create event_menu_mappings table for holiday/event-specific menus
-- Corresponds to qrate-core migration 021_create_event_menu_mappings.sql

CREATE TABLE IF NOT EXISTS event_menu_mappings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(100) NOT NULL,
    -- e.g. "St_Patricks_Day", "Super_Bowl", "Valentines_Day", "New_Years_Eve"
    restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
    menu_item_ids UUID[] NOT NULL DEFAULT '{}',
    active_from TIMESTAMP WITH TIME ZONE,
    active_until TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS event_menu_mappings_restaurant_idx
    ON event_menu_mappings (restaurant_id);

CREATE INDEX IF NOT EXISTS event_menu_mappings_event_type_idx
    ON event_menu_mappings (event_type);

CREATE INDEX IF NOT EXISTS event_menu_mappings_active_idx
    ON event_menu_mappings (active_from, active_until)
    WHERE active_from IS NOT NULL AND active_until IS NOT NULL;

COMMENT ON TABLE event_menu_mappings IS
    'Maps special events/holidays to curated menu item selections per restaurant';
