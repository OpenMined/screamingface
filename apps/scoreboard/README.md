# scoreboard

Public benchmark scoreboard service for ScreamingFace clients. It ingests benchmark scores and serves leaderboard data in follow-up tickets; this scaffold only provides the runnable service shell, health route, settings, database wiring, migrations configuration, and test/tooling baseline.

## Quick Start

```bash
cd apps/scoreboard
uv sync

SCOREBOARD_DATABASE_URL='sqlite://:memory:' uv run uvicorn scoreboard.main:app --port 9106 --reload

# Sanity check
curl -sf http://localhost:9106/healthz
```

`/healthz` is a liveness probe only. It does not query the database and does not prove Postgres connectivity; a real readiness probe belongs with the first concrete score model in D-SCORE-002.

### Running Against Local Postgres

The default `SCOREBOARD_DATABASE_URL` expects a local Postgres database at `postgres://scoreboard:scoreboard@localhost:5432/scoreboard`.

```bash
docker run --rm -d --name sf-scoreboard-postgres \
  -e POSTGRES_USER=scoreboard \
  -e POSTGRES_PASSWORD=scoreboard \
  -e POSTGRES_DB=scoreboard \
  -p 5432:5432 \
  postgres:16-alpine

uv run uvicorn scoreboard.main:app --port 9106 --reload
```

Aerich is configured in `aerich.toml`, not `pyproject.toml`; use `-c aerich.toml` for Aerich commands. D-SCORE-002 will add the first concrete score models and migrations. Once migrations exist, apply them with `uv run aerich -c aerich.toml upgrade`.

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
uv run pyright
```

Unit tests use SQLite so the scaffold can be validated without a local Postgres server. Postgres-backed tests can opt into the shared per-test schema fixture by setting `SCOREBOARD_TEST_DATABASE_URL`.

## Layout

```
src/scoreboard/
  main.py            FastAPI app + Tortoise lifespan
  config.py          Settings
  cli.py             `scoreboard` console-script entry point
  db.py              Tortoise configuration/init helpers
  routes/
    health.py        GET /healthz
  scores/models/     Empty model package reserved for D-SCORE-002
tests/
  unit/
```
