# Developer Notes — qrate-ai-recommender

## Architecture Decisions

### Why pgvector instead of a dedicated vector DB?
The existing QRate PostgreSQL (RDS menucrawler) already has all menu data. Adding pgvector as an extension avoids a second infrastructure dependency and keeps vector search co-located with the allergen/dietary filter query (Step 1 + Step 2 run in the same DB session).

### Why Claude for both reasoning and cross-sell (not a scoring formula)?
Personalized pitch language is the core value — a formula can rank items but can't say "Since it's your birthday and you love citrus, our Salmon is the perfect treat tonight." Claude generates warm, contextual language while also handling the ranking logic. The upsell threshold (`margin_score > 7.0`) is enforced programmatically before Claude is called.

### Why Titan Embeddings v2 for menu items?
Same Bedrock client, no new credentials. 1536-dim output matches text-embedding-3-large quality for food description similarity. All menu items are embedded once (batch script) and stored in the `embedding_vector` column — inference only happens for the guest query vector at request time.

### Session storage: DynamoDB over PostgreSQL
Matches the AI Waiter pattern exactly. 1-hour TTL, no cleanup needed, scales horizontally. PostgreSQL is for durable data; DynamoDB is for ephemeral session state.

## Integration Points with Existing Repos

| This service reads from | QRate repo | Table/resource |
|---|---|---|
| Menu items + food_tags | qrate-core | `menu_items` |
| Guest allergens + preferences | qrate-core | `diner_profiles` |
| Restaurant context | qrate-core | `restaurants` |
| Session state | qrate-core (AI Waiter pattern) | DynamoDB `recommendation-sessions-{env}` |

## Known Limitations / Future Work

- **Hard filter uses string matching on allergen arrays** — works for known allergens but won't catch unlisted ingredients. A richer ingredient-level allergen graph would improve safety further.
- **Cross-sell drink detection** — currently simplified (checks food_tags category string). Should fetch actual cart item data from the order service.
- **Environmental location signals** — weather and PredictHQ require lat/lon from the client. Current API doesn't expose a location field; add to `RecommendRequest` when frontend is ready.
- **Embedding freshness** — if a restaurant updates menu item descriptions, embeddings go stale. A webhook from the menu service triggering re-embedding would keep vectors fresh.
- **IVFFlat index** — requires `VACUUM ANALYZE` after bulk inserts and `lists` tuning based on row count. For < 10k items, a flat (brute-force) index may outperform IVFFlat.

## Migration Order for qrate-core

```
018_add_embedding_vector.sql          ← migrations/001_add_embedding_vector.sql
019_add_margin_upsell.sql             ← migrations/002_add_margin_score_upsell_cross_sell.sql
020_extend_diner_profiles.sql         ← migrations/003_extend_diner_profiles.sql
021_create_event_menu_mappings.sql    ← migrations/004_create_event_menu_mappings.sql
```

`000_enable_pgvector.sql` must run **once** on the RDS instance by a superuser before migration 018.
