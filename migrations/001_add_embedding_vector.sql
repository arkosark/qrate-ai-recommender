-- Migration 001: Add embedding_vector column to menu_items
-- Corresponds to qrate-core migration 018_add_embedding_vector.sql

ALTER TABLE menu_items
    ADD COLUMN IF NOT EXISTS embedding_vector vector(1536);

-- IVFFlat index for approximate nearest neighbor search
-- lists=100 is a reasonable default for up to ~1M rows; tune with VACUUM ANALYZE
CREATE INDEX IF NOT EXISTS menu_items_embedding_ivfflat_idx
    ON menu_items
    USING ivfflat (embedding_vector vector_cosine_ops)
    WITH (lists = 100);
