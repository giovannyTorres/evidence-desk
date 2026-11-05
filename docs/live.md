# Activate LIVE explicitly

No external call has been verified in this workspace. Ordinary tests use simulated SDK HTTP transports. The following opt-in steps can incur provider costs and were not executed.

1. Copy `.env.example` to `.env` locally, keep it out of Git and restrict permissions (`chmod 600 .env`). Set `MODE=LIVE`, `PROVIDER=openai`, `MODEL=gpt-4.1-mini` and a valid `OPENAI_API_KEY`. OpenAI embeddings are required for either generation provider.
2. For Gemini, set `PROVIDER=gemini`, `MODEL=gemini-2.5-flash`, and `GEMINI_API_KEY`, retaining the OpenAI key for embeddings. Providers are not interchangeable: Gemini uses its own JSON schema/config API; OpenAI uses strict chat JSON schema. Select a model supporting the configured structured response, temperature and streaming capabilities. Unsupported model/parameter combinations fail visibly; no automatic provider or DEMO fallback exists.
3. Configure `PUBLIC_ORIGIN` to the exact browser origin; use `COOKIE_SECURE=true` under HTTPS. Start/recreate API and worker with `docker compose up --build -d --wait`. `/api/config` lists missing configuration without exposing values.
4. Create a LIVE user, using an email distinct from the public DEMO identities: `docker compose exec api python -m evidence.provision --email reviewer@portfolio.example --org aurora --name Reviewer`. Enter the password at the protected prompt. DEMO accounts/cookies cannot access LIVE.
5. Sign in, upload original synthetic documents and wait for ready. The worker extracts text and calls OpenAI embeddings. Every index records provider, model and dimensions. Change embedding settings only with reindexing: `POST /api/documents/{id}/retry` rebuilds that immutable current version while keeping stable excerpt IDs. Configuration mismatches block vector queries, even if other indexes would match.
6. Ask a free-form question. Authentication and tenant filtering occur before retrieval. Invalid model references are rejected; unsupported questions abstain. Provider errors remain LIVE errors. Timeouts are bounded; OpenAI has two retries, Gemini three total attempts; concurrency is limited per API process. Each request has an overall timeout. UI cancellation interrupts the active task.
7. To verify actual providers after intentionally authorizing costs, run locally: `RUN_LIVE=1 PYTHONPATH=services/api uv run pytest -m live tests/test_live.py -q`. Run once with each provider configuration. The smoke test validates a cited structured answer and embedding dimensions, not general model quality.

Secrets stay in backend environment variables; never put them in `NEXT_PUBLIC_*`. `MODEL_TIMEOUT`, `MODEL_CONCURRENCY`, `MAX_OUTPUT_TOKENS`, `TEMPERATURE`, `EMBEDDING_MODEL` and `EMBEDDING_DIMENSIONS` are backend settings. DEMO has no token counts. LIVE token telemetry is currently not persisted because generation uses provider streaming deltas; it is not estimated or fabricated.

## Evaluation

`fixtures/evaluation.json` contains at least 40 prompts and expected document/section/abstention/organization. The LIVE evaluation runner writes measured evidence/abstention checks only; it does not claim factual correctness or model immunity. `RUN_LIVE=1 PYTHONPATH=services/api uv run python -m evidence.evaluate --output live-evaluation.json` requires an indexed LIVE corpus and paid API credentials. Keep development and final splits separate when tuning. No model metrics exist until this command is executed successfully.

## Audited provider contract and capability boundaries

The adapter accepts only the reviewed structured-streaming profiles in `Settings.supports_generation()`: GPT-4.1/mini/nano and their 2025-04-14 snapshots; GPT-4o (2024-08-06 / 2024-11-20), GPT-4o-mini (2024-07-18), their aliases; Gemini 2.5 Flash/Pro. This checks request capabilities, **not current model availability or account entitlement**. For a different model, review its provider contract and add the corresponding tested profile before selecting it. Reasoning models with different temperature requirements are not silently treated as GPT-4.1. The OpenAI request uses `max_completion_tokens`; Gemini uses `max_output_tokens` and its own schema configuration.

A parseable JSON payload is insufficient evidence of completion. OpenAI must terminate its sole candidate with `finish_reason="stop"`; Gemini must terminate with `STOP`. Length limits, refusal, filtering, safety blocks, unexpected tool calls, missing terminal events and invalid typed output fail safely. Gemini automatic continuation and automatic function execution are disabled, and thought parts never enter the answer. Structured output is bounded to 65,536 characters and validated before the HTTP chat emits answer text. DEMO cannot invoke either generation or embeddings even when keys are present.

Embeddings use an explicit float encoding, validate the returned model, contiguous unique input indices, finite coordinates and configured dimensions. Only `text-embedding-3-small` (up to 1536 dimensions) and `text-embedding-3-large` (up to 3072) have reviewed dimensions support. An incompatible embedding model is rejected as configuration rather than indexed under an incorrect identity. Model requests include concurrency-queue time in the deadline. API lifespan, ingestion and evaluation callers close SDK resources; cancellation closes active streams. Safe exceptions omit original provider bodies, and model spans disable automatic exception-stack capture.

The audited transport tests are in `tests/test_providers.py`; they use official SDKs with HTTP fixtures for success and failure, not external inference. Provider contract sources consulted on 2026-11-05:

- [OpenAI official streaming response types](https://github.com/openai/openai-python/blob/main/src/openai/types/chat/chat_completion_chunk.py): stop/length/content-filter/tool finish reasons and refusal deltas.
- [OpenAI official embeddings client](https://github.com/openai/openai-python/blob/main/src/openai/resources/embeddings.py): dimensions and encoding parameters.
- [OpenAI SDK lifecycle and retries](https://github.com/openai/openai-python): connection closure and bounded retry configuration. The platform API-reference pages returned HTTP 403 in this environment; the official SDK source was accessible.
- [Gemini GenerateContent API](https://ai.google.dev/api/generate-content): prompt blocking, candidate parts, finish reasons and usage events.
- [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output) and [official Python SDK](https://github.com/googleapis/python-genai): schema configuration, asynchronous closure and continuation controls.

These contracts still require the documented opt-in LIVE smoke with real credentials before claiming external service verification. No such call was made in this audit.
