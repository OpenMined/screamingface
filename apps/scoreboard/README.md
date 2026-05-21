# scoreboard

Public benchmark scoreboard service for ScreamingFace clients. It now provides the runnable service shell, health route, settings, Tortoise database wiring, score-domain models, the initial migration, and the persistence/query store. HTTP ingestion and leaderboard routes land in follow-up tickets.

## Quick Start

```bash
cd apps/scoreboard
uv sync

uv run tortoise migrate
uv run uvicorn scoreboard.main:app --port 9106 --reload

# Sanity check
curl -sf http://localhost:9106/healthz
```

`/healthz` is a liveness probe only. It does not query the database and does not prove Postgres connectivity.

### Running Against Local Postgres

The default `SCOREBOARD_DATABASE_URL` expects a local Postgres database at `postgres://scoreboard:scoreboard@localhost:5432/scoreboard`.

```bash
docker run --rm -d --name sf-scoreboard-postgres \
  -e POSTGRES_USER=scoreboard \
  -e POSTGRES_PASSWORD=scoreboard \
  -e POSTGRES_DB=scoreboard \
  -p 5432:5432 \
  postgres:16-alpine

uv run tortoise migrate
uv run uvicorn scoreboard.main:app --port 9106 --reload
```

Tortoise's built-in migration CLI is configured through `[tool.tortoise]` in `pyproject.toml`. Apply migrations with `uv run tortoise migrate`; running it a second time should be a no-op.

### Migration Verification

```bash
cd apps/scoreboard
uv run tortoise migrate
uv run tortoise migrate
```

The first run applies pending migrations. The second run should report that no migrations are pending.

## Configuration

Settings are read from environment variables with the `SCOREBOARD_` prefix.

| Variable | Default | Description |
| --- | --- | --- |
| `SCOREBOARD_HOST` | `127.0.0.1` | Host used by the `scoreboard` console script. |
| `SCOREBOARD_PORT` | `9106` | Port used by the `scoreboard` console script. |
| `SCOREBOARD_LOG_LEVEL` | `info` | Uvicorn log level. |
| `SCOREBOARD_DATABASE_URL` | `postgres://scoreboard:scoreboard@localhost:5432/scoreboard` | Tortoise database URL. |
| `SCOREBOARD_CORS_ORIGINS` | `["*"]` | JSON list of allowed CORS origins. |

`SCOREBOARD_CORS_ORIGINS` defaults to `["*"]` because the scaffold has no authenticated routes and never sets cookies. D-SCORE-007 will tighten this once the leaderboard write path lands.

## Development

```bash
cd apps/scoreboard
uv run pytest tests/unit/ -v
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

Unit tests use SQLite through Tortoise's isolated `tortoise_test_context`, so the persistence layer can be validated without a local Postgres server. Postgres-backed tests can opt into a database URL by setting `SCOREBOARD_TEST_DATABASE_URL`.

## Layout

```
src/scoreboard/
  main.py            FastAPI app + Tortoise lifespan
  config.py          Settings
  cli.py             `scoreboard` console-script entry point
  db.py              Tortoise configuration/init helpers
  routes/
    health.py        GET /healthz
  scores/
    schemas.py       Pydantic DTOs for submissions and read models
    store.py         Tortoise-backed persistence/query store
    models/          Benchmark, Score, and IdempotencyKey Tortoise models
    migrations/      Tortoise built-in migrations
tests/
  unit/
```
