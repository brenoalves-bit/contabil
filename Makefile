.PHONY: install migrate run test lint admin
install: ; uv sync
migrate: ; uv run alembic upgrade head
run: ; uv run uvicorn app.main:app --reload --port 8000
test: ; uv run pytest -q
lint: ; uv run ruff check app tests scripts
admin: ; uv run python scripts/bootstrap_admin.py --email $(EMAIL) --nome "$(NOME)" --senha '$(SENHA)'
