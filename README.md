# Card Game Django

## DevOps setup

- Docker build: `docker build -t card-game-django .`
- Docker Compose: `docker compose up --build`
- Environment template: `.env.example`
- CI workflow: `.github/workflows/ci.yml`

## Local development

1. Copy `.env.example` to `.env`.
2. Install dependencies with `uv sync`.
3. Run migrations and the server:
   - `uv run python manage.py migrate`
   - `uv run python manage.py runserver`

## Game backend

The Django app implements a simplified two-player Battle game.

- `game/models.py` contains the structural data model: `Profile`, `Game`, `GamePlayer`, `Card`, `Deck`, `DeckCard`, `Round` and `MoveLog`.
- `game/game_engine.py` is the only place that applies game rules: creating, joining, starting, drawing, resolving rounds and finishing games.
- `game/serializers.py` serializes the state according to the connected user. A played card is visible to its owner immediately, hidden from the opponent until the round is resolved, and both cards become visible after player 2 plays.
- Mutating views are protected with `login_required` and `require_POST`; CSRF remains enabled.

The "Ajouter une carte" action must POST to:

```text
/games/<game_id>/play-card/
```

The request must not send a card id, rank, suit, score, round number, winner or status. The server derives all of those values from the authenticated user and the locked game state.

Migration `game.0002_backend_refactor` preserves the initial `GameCard` table by renaming it to `DeckCard`, then linking existing rows to the new `Card` and `Deck` models.
