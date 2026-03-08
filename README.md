# qrate-ai-recommender

Dedicated AI recommendation microservice for the QRate dining platform.

## What It Does

Provides semantic, context-aware menu recommendations via a 4-step pipeline:

1. **Hard Filter** — removes allergen/dietary violations (safety-first, pure SQL)
2. **Semantic Search** — converts guest intent → Titan embedding → pgvector cosine similarity
3. **Agentic Reasoning** — Claude re-ranks by margin score, injects environmental context, generates personalized pitch
4. **Cross-Sell** — on item acceptance, Claude suggests the best pairing (drink/side)

## Architecture

| Concern | Technology |
|---|---|
| Language | Python 3.11 |
| Framework | FastAPI 0.109+ |
| Database | PostgreSQL + pgvector (existing RDS) |
| Embeddings | Amazon Titan Embeddings v2 (via Bedrock) |
| AI Reasoning | AWS Bedrock (Claude Sonnet) |
| Sessions | DynamoDB (same pattern as AI Waiter) |
| Auth | AWS Cognito JWT |
| Port | 8004 |

## Quick Start

### Unit Tests (no Docker needed)

```bash
pip install -r requirements.txt
pytest tests/unit/ -v
```

### Local E2E Stack

```bash
# 1. Start full local stack (PostgreSQL + LocalStack + WireMock + service)
docker-compose up -d

# 2. Seed DB with test fixtures
python tests/fixtures/seed_local_db.py

# 3. Generate mock embeddings for local menu items
python scripts/generate_embeddings.py --local --restaurant-id r0000000-0000-0000-0000-000000000001

# 4. Run E2E tests
pytest tests/e2e/ -v

# 5. Health check
curl http://localhost:8004/health

# 6. Manual test
curl -X POST http://localhost:8004/api/v1/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "guest_id": null,
    "session_id": "test-1",
    "restaurant_id": "r0000000-0000-0000-0000-000000000001",
    "message": "something spicy and crunchy",
    "visit_context": "Date Night",
    "cart_items": []
  }'

# 7. Tear down
docker-compose down -v
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/recommend` | Main recommendation pipeline |
| `POST` | `/api/v1/menu/enrich-embeddings` | Batch embed menu items (auth required) |

## Environment Variables

See `.env.example` for all required variables.

Key variables:
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` — same as other QRate services
- `BEDROCK_MODEL_ID` — `anthropic.claude-sonnet-4-6`
- `TITAN_EMBEDDING_MODEL_ID` — `amazon.titan-embed-text-v2:0`
- `DYNAMODB_SESSIONS_TABLE` — `recommendation-sessions-{env}`
- `PORT` — `8004`

## Database Migrations

4 SQL migrations must run against the shared `menucrawler` database:

```bash
# Add to qrate-core as migrations 018-021
migrations/000_enable_pgvector.sql      # Enable pgvector extension (run first, once)
migrations/001_add_embedding_vector.sql  # Add vector column to menu_items
migrations/002_add_margin_score_upsell_cross_sell.sql  # Add recommender columns
migrations/003_extend_diner_profiles.sql  # Add preference_map, context_history, etc.
migrations/004_create_event_menu_mappings.sql  # New table for holiday/event menus
```

## Deployment

Follows the same ECS Fargate pattern as existing QRate services:

```
Docker image → ECR (qrate-ai-recommender)
ECS service: ai-recommender-{env}
Cluster: restaurant-app-cluster-{env}
Port: 8004
```

Add the CDK stack to `qrate-core/infrastructure-cdk/` following existing service patterns.

## Agent Priority Hierarchy

1. **Safety** — allergen hard block, always enforced
2. **Intent** — semantic match to guest's explicit request
3. **Upsell** — premium suggestion if `margin_score > 7.0`
4. **Cross-sell** — complete the meal if cart has no drink

## Key Test Scenarios

| Scenario | What It Proves |
|---|---|
| Nut allergy guest → never sees peanut tacos | Safety guarantee |
| "Light citrus" → citrus dishes returned | Semantic search works |
| High margin item wins over lower match | Upsell logic correct |
| Accepting tacos → margarita suggested | Cross-sell triggers |
| Date Night context → premium upsells | Environmental signals |
| Birthday guest → special pitch | Occasion awareness |
| 5000 synthetic personas pass safety | No allergen leaks |
