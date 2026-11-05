# Technical audit — 2026-11-05

## Scope and starting state

Reviewed baseline **`32aac6d`**, branch `main`, clean worktree. No applicable root/repository `AGENTS.md` was present. Existing Git history and original named database volumes were preserved. Tests use a new `evidence_audit_test` database; clean-container validation uses Compose project `audit-evidence` and its own volume, never the existing `evidence-desk` data.

This is a portfolio review candidate, not a production certification. No external model service was called. No API key, paid call, cloud resource, push or publication was used.

## Findings and corrections

| ID / impact | Observed defect and reproduction | Minimal correction and regression evidence |
|---|---|---|
| E01 / High | `providers.py` accepted complete JSON even when OpenAI ended with `finish_reason=length`, Gemini with `MAX_TOKENS`/`SAFETY`, or transport ended without a terminal state. The original `32aac6d` module was executed with the official OpenAI SDK and a MockTransport SSE containing valid Answer JSON followed by `length`; it returned an Answer. | Require OpenAI `stop` / Gemini `STOP`; reject refusals, truncation, block reasons, unexpected tools, absent terminals and invalid schema. `tests/test_providers.py` uses real SDK serialization and documented terminal/error shapes, including 401/429/503 and connection cancellation. |
| E02 / High | A direct call to a DEMO gateway with keys could invoke an API, and Gemini's SDK could automatically continue generation. | Adapter boundary refuses inference in DEMO regardless of keys; Gemini continuation and automatic tool execution disabled. Model capability profiles and bounded parameters are explicit. Contract tests assert zero network calls from DEMO. |
| E03 / High | `upload()` checked 5 MiB only after multipart parsing and synchronously extracted PDF on the API event loop, then repeated extraction in the worker. A compressed/pathological document could consume API resources before the job existed. | 6 MiB whole-request ASGI limit before multipart parsing, including chunked bodies; cheap format/UTF-8 checks only at upload. Worker parses in a subprocess with 512 MiB memory, 8 CPU seconds, 10 wall seconds and two parser slots per process. A signature-valid malformed PDF now becomes a durable error job, with retry, rather than blocking an API parser. `test_direct_backend_bounds_declared_and_streamed_request_body`, `test_pdf_parse_failure_is_durable_retryable_worker_state`; real browser error/retry/delete flow. |
| E04 / High | An expired slow indexing worker could overwrite a newer reclaimed attempt after lease expiry. | Transactionally compare the claimed attempt as a fencing token before success/failure writes. Actual concurrent coroutine test suspends worker one, expires its database lease, completes worker two, then releases worker one and verifies worker two's vector remains. |
| E05 / Medium | Uploading content equal to historical v1 while v2 was current returned v1 but left v2 current; the claimed idempotence contradicted the upload result. | Deduplicate only against the current version; restoring historical content creates v3. Regression checks actual downloaded current bytes and repeated v3 idempotence. |
| E06 / Medium | Lexical search included chunks belonging to a failed/reprocessing index; nullable model/dimension metadata could escape compatibility checks. | Search requires a ready current version, and hybrid retrieval rejects incomplete/incompatible metadata. Existing PostgreSQL/pgvector tenant-isolation tests and new failed-index search test run against real PostgreSQL. |
| E07 / High | Tests defaulted to the application's `DATABASE_URL` and drained processing jobs or temporarily changed seeded fixture hashes in that database. | `tests/conftest.py` sets a separate `TEST_DATABASE_URL`, requires a database name ending `_test`, ignores application database configuration, and clears model credentials unless LIVE smoke opt-in is explicit. CI and README now provide the isolated database setup. |
| E08 / Medium | SDK clients were never explicitly closed by API shutdown, per-job embedding gateways or evaluation runs. Raw provider exceptions could enter exported model spans; search queries could enter automatic HTTP URL spans. | `aclose()` in lifecycle/finally blocks, stream cancellation closes resources, sanitized provider errors and no automatic model exception recording. HTTP hooks remove query strings and the duplicate raw Uvicorn access logger is disabled. Both an in-memory exported span test and an actual Uvicorn subprocess with console tracing assert that a query canary is absent; structured request logs remain present. |
| E09 / Medium | Browser accepted SSE EOF without a terminal event and silently replaced the incomplete answer with history; an error index received a pending badge. Organization display inferred contracts not returned by the API. | Detect missing browser terminal event, show a retryable error, style `error` correctly, and derive organization from the actual `org` field. Browser regression simulates a truncated transport then completes a new real conversation. |
| E10 / Low | Small muted text `#737c76` on `#faf9f6` had measured contrast about 4.09:1. | Darkened muted text to `#626c66`; desktop/mobile screenshots reviewed. This is a targeted readability correction, not comprehensive WCAG certification. |
| E11 / Medium | A configuration outage left DEMO credentials prefilled while mode was unknown; sign-in remained available. | Start blank, prefill only after confirmed DEMO, block sign-in until mode is known, and offer a connection retry. Browser contract tests verify LIVE stays blank and failed configuration recovers without pretending to be DEMO. |
| E12 / Medium | Managed-workspace CA trust existed only at build time, so SDK HTTPS would fail certificate validation inside running API/worker containers behind that proxy. | The optional cloud override mounts the combined CA bundle read-only at runtime and sets `SSL_CERT_FILE`; standard Compose stays portable. A public HTTPS GET (not a model request) verifies runtime TLS. Docker build context also excludes logs/caches/reports. |
| E13 / High | A direct overlong or wrong-type password submitted to `/api/auth/login` returned `422` with the credential repeated in FastAPI's default `detail[].input`; the original response was reproduced through the actual ASGI app. | A `RequestValidationError` handler returns only field location, error type and a fixed safe message, excluding raw input/context or custom validator text. `test_invalid_credentials_are_not_reflected_in_validation_errors` checks length/type failures and absence of a synthetic credential canary from responses and captured logs. |

## Manual grounding review

The corpus contains **five** original manuals: four Aurora topics and Meridian's travel manual. These checks are human/code inspection of synthetic documents, not model-quality measurements.

| Evaluation item | Verified source/expectation |
|---|---|
| eval-001 | `fixtures/manuals/aurora/travel.md`, Booking: domestic travel at least **10 calendar days** ahead. |
| eval-007 | Same file, Changes: cancellation reported to the travel coordinator within **one working day**. |
| eval-015 | `purchases.md`, Receiving: invoice identifies **order number and goods received**. |
| eval-024 | `reimbursement.md`, Review explicitly **does not guarantee a payment date**. |
| eval-034 | `security.md`, Documents: embedded instructions are **content, not operational commands**. |
| eval-040 | No annual procurement budget exists in the supplied corpus; abstention expectation is justified. |
| eval-044 | Meridian has no authorized source for Aurora cancellation procedure; its own manual says Aurora policy does not apply. Isolation/abstention is expected. |

## Reproducible validation

The application needs only its repository, Docker/Compose, PostgreSQL with pgvector and the app images. No files from another portfolio project are imported. Host development additionally requires Python 3.12, uv, Node and npm; browser tests require Chromium installed through Playwright or an explicit system-browser path.

```sh
uv sync --frozen
cd apps/web && npm ci && cd ../..
# Create a disposable DB on the documented development PostgreSQL service first:
# createdb -h localhost -p 5541 -U evidence evidence_test
TEST_DATABASE_URL=postgresql+psycopg://evidence:evidence@localhost:5541/evidence_test uv run pytest -q -m 'not live'
uv run ruff check services tests
uv run mypy services/api/evidence services/worker
cd apps/web && npm run lint && npm run typecheck && npm test && npm run build
```

The isolated audit run uses `evidence_audit_test` instead of `evidence_test`. The rejected `_test` guard occurs before importing application modules/connecting to PostgreSQL. The test database is deliberately mutable; do not put personal data there.

Fresh Docker reproduction (Compose supporting `!override` is required):

```sh
docker compose -p audit-evidence -f compose.yaml -f compose.cloud.yaml -f infra/compose.audit.yaml build --pull --no-cache
docker compose -p audit-evidence -f compose.yaml -f compose.cloud.yaml -f infra/compose.audit.yaml pull db
docker compose -p audit-evidence -f compose.yaml -f compose.cloud.yaml -f infra/compose.audit.yaml up -d --wait
WEB_URL=http://localhost:3201 PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm --prefix apps/web run test:e2e
uv run python tests/audit_restart.py --cloud
# Preserve the audit volume for inspection:
docker compose -p audit-evidence -f compose.yaml -f compose.cloud.yaml -f infra/compose.audit.yaml down
```

Omit `compose.cloud.yaml` and the restart script's `--cloud` flag on hosts that use normal public CA trust. The optional managed-workspace override supplies the combined CA bundle during builds and mounts it read-only at runtime for API/worker SDK HTTPS; TLS is never disabled. The audit profile gives its own web port 3201 and PostgreSQL port 5641. Do not use `--no-build` as proof of reconstructibility.

## Execution record and limits

- Backend: **74 tests passed** in the final integrated suite after E13, 1 LIVE marker excluded, against real PostgreSQL/pgvector on the isolated audit database. Includes **43 provider/configuration contract tests** and both invalid-credential regressions; neither count is a model evaluation score. Python lint and mypy also pass after the validation-handler correction.
- Python lint and mypy (15 modules), frontend lint/TypeScript, 6 frontend unit tests and production Next build passed.
- Initial browser audit found a test locator ambiguous with Next's accessibility announcer; scoped it to the visible application error without weakening the intended error/recovery assertion.
- **Clean Docker reconstruction passed**, with `build --pull --no-cache`, an explicit pull of `pgvector/pgvector:0.8.0-pg17`, and a new `audit-evidence_postgres` volume. API, worker, web and database were all healthy. This resolved the previous registry uncertainty; no old application image, installed host package or file outside the build context supplied application code. The sole environment-specific dependency is the documented optional CA bundle. The post-build `up --no-build --wait` booted the images just rebuilt; it is not the build evidence.
- **7 Playwright flows passed against the fresh containers**: sample answer/source/history; actual upload and mobile layout; keyboard focus and DEMO free-form explanation; malformed PDF error/retry/delete/empty search; truncated SSE with a new successful conversation; confirmed LIVE login configuration; and UNKNOWN mode configuration failure/retry. The last two deliberately intercept only the configuration HTTP response, and the truncation case deliberately intercepts one stream; these are UI failure contracts, not external LIVE validation. [Screenshots](screenshots/) were captured after the fixes and visually reviewed at desktop and 390px mobile width.
- **Actual database/API/worker restarts passed**. [The compact execution record](audit-restart.json) was generated by [the repeatable restart script](../tests/audit_restart.py): a queued upload and its exact bytes survived database restart, the worker resumed it, sessions survived API restart, and saved messages/citations survived API/worker restart. Deleting the test document revoked its source. Mid-attempt worker lease recovery is tested separately with real PostgreSQL concurrency, not claimed from this queued-job check.
- Independent direct HTTP checks through the fresh web container returned unauthenticated library `401`; Aurora source `200` with Travel Handbook v1/Meals; arbitrary DEMO question `422`; Meridian direct access to that source, file, deletion and conversation `404`; and no Meridian lexical results for Aurora's `650` allowance.
- Public HTTPS from the API container to `https://pypi.org/simple/openai/` returned **200** using runtime CA trust. This verifies TLS/connectivity only; no model endpoint was called.
- The running container's OpenAPI document was fetched and checked in. Azure Bicep compiled locally with the available Bicep CLI; no Azure resource was created and Azure runtime validation remains pending.

After the final E13 correction, `build --pull --no-cache api worker` successfully reconstructed both affected backend images again. The database/API/worker started healthy on the preserved isolated audit volume. Direct HTTP **inside the rebuilt API container** verified both invalid password cases return `422` without the canary; actual structured logs include those `422` events without the credential. Valid login, a new upload processed by the real worker, source retrieval and deletion/revocation also passed. An independent second request reproduced the sanitized `422`. The frontend did not change after its full build and seven browser checks; those checks were not repeated or relabeled as new runs.

To reproduce the credential check after booting `db api worker`, without making a model call:

```sh
docker compose -p audit-evidence -f compose.yaml -f compose.cloud.yaml -f infra/compose.audit.yaml exec -T api python - <<'PY'
import httpx
marker = 'AUDIT_INVALID_PASSWORD_'
response = httpx.post('http://localhost:8000/api/auth/login', json={
    'email': 'analyst@aurora.example', 'password': marker * 12})
assert response.status_code == 422 and marker not in response.text
assert all(set(error) == {'loc', 'type', 'msg'} for error in response.json()['detail'])
print('422: credential omitted; field and error type retained')
PY
```

Final validated application image identities (local, not published):

| Image | SHA-256 |
|---|---|
| `audit-evidence-api` | `5d65d10b165b3eb2b6814d8e747305f8d64ca83e2161096da5ff678b699f4cd9` |
| `audit-evidence-worker` | `3486c6cb66f1fa4661ea45250a6b6e69409c27a6d24b23bf640fb65e549c92c3` |
| `audit-evidence-web` | `8cec90bfb707ad603898a62e75536e586aba708cbaafe79a0f7fed151e93f09b` |

The audit stack was stopped without removing its named volume after each validation. Original application volumes were also preserved. The earlier audit web image and intermediate build cache were removed to accommodate sequential builds of all three repositories on the workspace's limited disk; the final backend images were retained. Image cleanup does not alter the recorded build or browser results. Host checks and browser tests are additional evidence; they do not substitute for the completed fresh Docker build.

LIVE remains unverified against external services. Contract fixtures cannot establish actual model availability, acceptance, grounding quality, safety, billing or quotas. Model profiles and source URLs are documented in [LIVE](live.md). A provider/model outside a reviewed profile fails configuration validation until its contract is explicitly reviewed.

The parser's CPU/memory limits require Linux (the supported Docker runtime); scanned PDFs/OCR are not supported. Local authentication has no SSO or centralized distributed rate limiting. Upload bytes and per-process inference/parsing concurrency are bounded, but there is no aggregate organization storage quota. The two-minute chat lease was replaced with a bound covering retrieval plus generation timeouts. Backend authorization, citation identity and index checks do not prove immunity to prompt injection or semantic correctness of cited claims. UI responses are rendered as escaped React text; imported Markdown is not executed as HTML.
