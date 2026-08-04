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
