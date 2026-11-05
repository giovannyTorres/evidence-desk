.PHONY: demo install check test types build
demo:
	docker compose up --build -d --wait
install:
	uv sync --frozen
	cd apps/web && npm ci
test:
	uv run pytest -q -m 'not live'
	cd apps/web && npm test
check:
	uv run ruff check services tests
	cd apps/web && npm run lint
types:
	uv run mypy services/api/evidence services/worker
	cd apps/web && npm run typecheck
build:
	cd apps/web && npm run build
