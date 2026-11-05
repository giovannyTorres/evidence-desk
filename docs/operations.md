# Operations, trust and limits

## Trust boundary

Browsers, filenames, document text and model responses are untrusted. The API authenticates an opaque SHA-256-stored session and applies organization and mode constraints to documents, file downloads, chunks, search and conversations. Conversations additionally belong to their author. Passwords use salted PBKDF2. SameSite Strict HttpOnly cookies and an exact configured Origin check protect browser mutations. The Next gateway is same-origin and does not accept arbitrary upstream destinations. Sign-in throttling is per-process and is appropriate only for this single-replica demo; use a shared limiter and SSO before a public multi-replica deployment.

The public demo passwords are not production secrets. LIVE users are provisioned through the backend operator CLI and cannot reuse DEMO sessions. A lost session can be revoked by deleting its hashed record; logout revokes immediately. Rotate a leaked provider key in the provider portal, replace the secret, restart API/worker and inspect correlation metadata. Never commit `.env`, tokens or real employer material. Rotate database credentials separately; back up persistent data before changes.

Documents are capped at 5 MiB, 100 PDF pages and 400 chunks, require UTF-8 for text, and reject invalid PDF signatures, encryption, empty/scanned content and binary text. A reverse-proxy body limit is also enforced by the web gateway. Extraction runs only in a worker subprocess with Linux memory/CPU/wall-time limits; the API validates cheap signatures and bytes. Both the direct API and web gateway bound whole request bodies before multipart parsing. Aggregate storage quotas and stronger host/container isolation remain deployment considerations. There is no antivirus or OCR claim.

Prompt-injection instructions are explicitly classified as untrusted document content. Access-control tests demonstrate backend enforcement, not guaranteed model behavior. Retrieval may return semantically related but insufficient excerpts; the model must abstain and the application requires citations, but automated semantic entailment is not implemented. Human source review remains necessary.

## Data lifecycle and recovery

`python -m evidence.migrate` applies numbered schema migrations under an advisory lock. API and worker run idempotent seed/migrations at start. The worker claims jobs with row locks; a crashed processing job becomes eligible after its five-minute lease. Failed jobs require explicit retry. Immutable versions plus stable chunk IDs make reindexing repeatable. A busy chat lease covers two configured model timeouts plus 30 seconds; interrupted generation is retried by the user rather than replayed automatically. Backups use PostgreSQL tooling and should include the full database; files are stored as bounded base64 in version rows.

`docker compose down` preserves volumes. `docker compose down -v` permanently deletes demo data and should only be used intentionally. Healthchecks cover database/API/web availability and worker process liveness; production monitoring must also alert on old queued jobs and processing errors. No SLA or throughput claim is made.

## Azure Container Apps

`infra/main.bicep` is compiled to `infra/main.json` using Bicep 0.48.1. The template places web/API/worker in one Container App with only web ingress, preserving localhost API routing and same-origin cookies. It accepts an **existing** TLS-enabled PostgreSQL database URL with vector extension enabled, reviewed image references, exact public origin and secret parameters. PostgreSQL provisioning is deliberately external to this template. The database identity needs migration rights for initial setup; least-privilege runtime separation is a production hardening step.

Compile: `bicep build infra/main.bicep`. Before any future deployment, build/push reviewed images, provide secrets through an approved secret store/pipeline, verify database connectivity and vector support, and run an Azure what-if with your own subscription. Container Apps scale is fixed at one replica because per-process rate/concurrency limits are used. Template compilation is **not deployment validation**. No Azure resources or external repositories were created during this task.

## Inspect local traces

Set `OTEL_CONSOLE=true` and restart API/worker to emit actual OpenTelemetry spans to their logs. Instrumented spans cover HTTP requests, document processing, hybrid retrieval, generation and embeddings. The exporter does not send data outside the application. Trace attributes exclude prompts, documents and secrets. Console export is disabled by default to keep local logs compact; an OTLP exporter is not configured. Request logs always include correlation IDs and measured server durations.


## Managed-workspace certificate trust

`compose.cloud.yaml` is an optional environment-specific override. It mounts the host combined CA bundle read-only into API/worker and sets `SSL_CERT_FILE` for official SDK HTTPS at runtime, in addition to BuildKit CA secrets for installation. Normal deployments use their normal system CA store and omit this file. The bundle is not an application secret and is never copied into image layers. TLS verification stays enabled.
