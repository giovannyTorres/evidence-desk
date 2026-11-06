# Evidence Desk

A source-first document workspace for the fictional Aurora Cooperative and Meridian Studio. Upload text documents, process them durably, ask a curated sample question, and open the exact versioned evidence. Original synthetic material only; this is a portfolio product, not a bank system or a regulatory compliance claim.

![Evidence Desk workspace](docs/screenshots/02-workspace.png)

## Run without credentials

Requirements: Git, Docker Engine with Compose v2, and an available port **3101**. No API keys, `.env` file, host Python/Node installation or GPU are needed for DEMO.

```sh
git clone https://github.com/giovannyTorres/evidence-desk.git
cd evidence-desk
docker compose up --build -d --wait
```

If the repository is already cloned, run the Compose command from its root. All further commands assume that directory unless stated otherwise.

Open **http://localhost:3101**. Sign in with `analyst@aurora.example` / `demo-evidence`. The second organization is `analyst@meridian.example` with the same demonstration password. These intentionally public accounts are DEMO only and cannot authenticate in LIVE. The first launch builds images; wait for healthchecks and document processing. PDF extraction occurs only in the worker with Linux process resource limits; malformed or scanned PDFs become retryable processing errors.

Start with the suggested meal allowance question, then open its citation to inspect the original document, version and section. Upload a small TXT or Markdown file from **Document library** to see real processing and persistence. The [two-minute walkthrough](#two-minute-demo) covers both organizations. `make demo` is an equivalent shortcut if Make is installed.

DEMO runs PostgreSQL, sessions, permissions, file extraction, versioning, a durable worker, chat history and SSE. The model decision is replaced by six named, hash-bound fixtures. Free-form interpretation requires LIVE. The search API is explicitly lexical (the library UI filters titles/filenames); no embeddings or model timing/token/quality metrics are fabricated.

See [the technical audit and reproducible evidence](docs/audit.md) for corrected failure cases, contract boundaries and clean-install validation.

For this managed workspace's HTTPS proxy, use `docker compose -f compose.yaml -f compose.cloud.yaml up --build -d --wait`. The optional override uses the host CA bundle for builds and mounts it read-only for API/worker HTTPS at runtime. Normal development machines use the standard command above.

### Check, stop and resume

```sh
docker compose ps                          # Database, API, worker and web should be healthy
docker compose logs --tail=40 api worker   # Inspect a processing/startup failure
docker compose down                        # Stop services; keep the database volume
docker compose up -d --wait                 # Resume the existing installation
```

Documents, sessions and conversations persist in the named PostgreSQL volume. API and worker apply migrations and idempotent seed data automatically. Use the same Compose files when stopping/resuming if you enabled the optional cloud override. Avoid `down -v` unless you intentionally want to delete that installation's data.

## What to review

- **Backend:** `services/api/evidence/` contains SQLAlchemy models, migrations, authorization, extraction, hybrid retrieval, provider adapters and FastAPI endpoints.
- **Worker:** `services/worker/main.py` reuses the domain layer and claims leased PostgreSQL jobs with `FOR UPDATE SKIP LOCKED`.
- **Frontend:** `apps/web/` is Next.js/React/TypeScript with a same-origin streaming API gateway.
- **Contracts:** `/api/docs` and `/api/openapi.json` through the web entry point, plus the checked-in `docs/openapi.json` contract.
- **Evidence:** [verification](docs/verification.md), [architecture](docs/architecture.md), [LIVE activation](docs/live.md), [Spanish guide](docs/GUIA_ES.md), [trust/operations](docs/operations.md).

## Quick automated check

For source development/tests, install **Python 3.12**, **uv 0.13.4**, **Node.js 22.18+** (validated with 24.22.1), npm and Make. Dependency versions are pinned in `uv.lock` and `apps/web/package-lock.json`.

```sh
make install       # uv sync --frozen + npm ci
make quickcheck
```

The quick check runs the existing official-SDK contract tests and frontend unit tests: structured streaming, terminal failures, retries, embeddings and SSE parsing. It needs **no running database, application or API credentials** and sends no inference requests. This is a useful first check; it does not replace the database-backed integration and browser tests below.

Without Make, run `uv sync --frozen`, `npm --prefix apps/web ci`, `uv run pytest -q tests/test_providers.py -m 'not live'`, and `npm --prefix apps/web test`.

## Local development and full validation

Create the development database container once. It is separate from the default Compose application's database:

```sh
docker run --name evidence-dev-db -p 127.0.0.1:5541:5432 \
  -e POSTGRES_USER=evidence -e POSTGRES_PASSWORD=evidence -e POSTGRES_DB=evidence \
  -d pgvector/pgvector:0.8.0-pg17
docker exec evidence-dev-db pg_isready -U evidence -d evidence
```

After `pg_isready` reports that connections are accepted, create the dedicated test database and run the full checks:

```sh
docker exec evidence-dev-db createdb -U evidence evidence_test
make check types test build
```

Tests use only `TEST_DATABASE_URL` (default `postgresql+psycopg://evidence:evidence@localhost:5541/evidence_test`), require a database name ending `_test`, and ignore the application `DATABASE_URL`. Never place personal data in a test database. Reuse it for later test runs; do not repeat `createdb` if it already exists. To resume the development database after stopping it, use `docker start evidence-dev-db`.

To run the application from source, use separate terminals from the repository root:

```sh
PYTHONPATH=services/api uv run uvicorn evidence.main:app --port 8101
# Separate terminals:
PYTHONPATH=services/api uv run python services/worker/main.py
npm --prefix apps/web run dev
```

Stop the Compose web service first if it already occupies port 3101. With the API and worker running, install Chromium using `cd apps/web && npx playwright install chromium`, then run `npm run test:e2e` from that directory. Playwright starts the already-built frontend automatically when needed. For an existing DEMO web instance, use `WEB_URL=http://localhost:3101 npm --prefix apps/web run test:e2e` from the root. System Chromium is supported through `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium`. Browser tests create synthetic documents/conversations, so use a DEMO installation you control. CI runs without external credentials.

## Implementation status

OpenAI and Gemini generation/structured streaming plus OpenAI embeddings use official SDKs. Both generation transports and OpenAI embeddings are tested through simulated HTTP transports. **No real provider call was made.** Live provider acceptance, model quality, production concurrency and Azure deployment remain unverified. [The LIVE guide](docs/live.md) gives explicit opt-in configuration and smoke-test commands for when credentials are available; they are unnecessary for DEMO and the quick check. Azure Bicep is compiled locally; no cloud resources have been created.

Forty-four synthetic evaluation prompts include expected evidence, abstention and cross-organization cases in `fixtures/evaluation.json`. These are evaluation inputs, not measured model performance. The deterministic domain assertions test access and evidence integrity, not immunity to prompt injection.

## Two-minute demo

1. **0:00–0:20:** Sign in to Aurora and point out the permanent DEMO label.
2. **0:20–0:50:** Select the meal allowance example, watch the response stream and open the source. Compare the answer with the 650 MXN sentence and version/section metadata.
3. **0:50–1:20:** Upload a small Markdown file; observe queued → processing → ready. Replace it as a new version and inspect history through the API.
4. **1:20–1:40:** Select the question without evidence to show abstention. Explain free-form LIVE activation and the missing-key status.
5. **1:40–2:00:** Sign in to Meridian; show its different library. Point reviewers to the direct-access/retrieval isolation tests and contract tests.

## Optional Auto Ontology integration

Reviewed semantic context can enrich LIVE retrieval through a pinned local glossary
or the real NVIDIA public GET API. It is off by default; organization, current
version and original chunk citations remain enforced by Evidence Desk. The local
three-arm adapter uses real Ollama embeddings and PostgreSQL retrieval, with
extractive output and separate goldens. See [setup, contracts and measurement
limits](docs/auto-ontology.md).
