# Initial implementation verification — baseline ab7fa39

This historical record describes the original implementation. For the current audited candidate, corrected contracts, fresh image builds and restart evidence, see [the technical audit](audit.md).

All model responses used in automated tests are explicitly fixtures. No external model endpoint was called.

| Check | Result | Scope |
|---|---|---|
| `uv run pytest -q` | 25 passed; 1 LIVE smoke skipped | Real PostgreSQL + pgvector, auth, cross-org direct access/retrieval, mode isolation, upload limits, versions, job lease recovery, deterministic citation IDs, SSE cancellation, synthetic PDF page provenance, structured references and SDK transports |
| `uv run ruff check services tests` | Passed | Python source/tests |
| `uv run mypy services/api/evidence services/worker` | Passed, 13 modules | Domain/application types; third-party SDK internals excluded from analysis |
| `npm run lint` / `npm run typecheck` | Passed | Final frontend sources |
| `npm test` | 6 passed | SSE parsing and API-safe error behavior |
| `npm run build` | Passed | Production Next build |
| `npm run test:e2e` | 3 passed | Real API/worker; document upload, sample question→SSE→source→reload, mobile overflow, keyboard focus and free-form DEMO explanation |
| `npm audit` | 0 vulnerabilities at execution | npm advisory inventory, not proof of general security |
| Final Docker Compose | All four services healthy; 3 Playwright tests passed again against the container stack | API/worker/web run as unprivileged users; credentials absent |
| Local OpenTelemetry export | Actual console span emitted | No external collector or model call |
| Bicep 0.48.1 compile | Passed | Template syntax/type validation only; no Azure deployment |
| OpenAI generation + embeddings | Simulated HTTP transport passed | Actual official SDK, SSE/schema/dimensions |
| Gemini generation | Simulated HTTP transport passed | Actual official SDK, streaming/schema payload |
| Real external API calls | Not executed | Credentials absent; model quality, provider acceptance and costs remain unmeasured |

The independent PDF HTTP smoke uploaded an original two-page PDF, observed real background extraction, retrieved Page 2, fetched the source, downloaded byte-identical original data and verified source 404 after deletion. See [independent review](INDEPENDENT_REVIEW.md).

Screenshots are real Chromium captures: [sign in](screenshots/01-sign-in.png), [workspace](screenshots/02-workspace.png), [answer and source](screenshots/03-answer-and-source.png), [library](screenshots/04-document-library.png), [mobile](screenshots/05-mobile-workspace.png). Desktop/source/mobile views were visually inspected. Keyboard/focus/mobile checks do not constitute full WCAG certification.

The 44-case evaluation dataset is an input inventory, not a model benchmark result. LIVE evaluation output is deliberately absent. Regression assertions demonstrate backend controls; they do not establish immunity to prompt injection.

Final container verification used `docker compose up --no-build -d --wait` after the documented CA-aware build. All four services were healthy. After successful browser checks, `docker compose down` stopped services to conserve this shared 32 GiB workspace; the named data volume and final images were retained. Restart with `docker compose up -d --wait` (no rebuild needed here).
