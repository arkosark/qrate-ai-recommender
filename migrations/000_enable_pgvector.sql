-- Must run before any other migrations
-- Enables pgvector extension on the menucrawler database
-- On AWS RDS: requires rds_superuser or the extension must be whitelisted
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
