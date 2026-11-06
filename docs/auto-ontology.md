# Optional reviewed semantic context

Evidence Desk can add a reviewed glossary or NVIDIA Auto Ontology context to its
existing hybrid retrieval. The default is `ONTOLOGY_MODE=off`. DEMO remains a
fixture experience and never calls NVIDIA. Production generation providers and
the Linux upload-extraction sandbox are unchanged.

The integration is a narrow public-API adapter, compatible with the contracts
inspected in NVIDIA commit
`c4495670947eb7b4616f0dd9900e5ced2a48ca1e` (source version 1.2.0). It calls
`GET /api/terms?query=<approved name>&skip=...&limit=50` and
`GET /api/terms/{id}` on the authenticated public gateway. It never submits SQL,
uploads documents to NVIDIA, or calls the internal trusted FastAPI port. The
name query is a substring search, not an embedding search of document content.
The server's own models are not required for these GET operations.
The official catalog exposes semantic terms represented by a catalog table;
orphan rows in the term table are not valid API fixtures. Curated imports must
preserve NVIDIA's required catalog relationships.

## Review and source boundaries

`ONTOLOGY_SNAPSHOTS` is an operator-controlled JSON map, keyed by `org:LIVE`:

```json
{"aurora:LIVE":{"path":"/reviewed/aurora.snapshot.json","sha256":"<exact file SHA256>"}}
```

Each file has `schema_version:1`, `application:"evidence-desk"`, `snapshot_id`,
`source` (`glossary` or `auto_ontology`), `source_commit`, `scope:{org,mode}`,
`certified:true`, `approved_by`, `terms`, and `bindings`. A binding contains
`term_id`, `chunk_id`, `document_id`, `document_version`, and `content_sha256`.
It points to the original application evidence, not an NVIDIA-generated citation.
The file is bounded to 512 KB and its exact digest must match configuration.
Changing a snapshot requires a separate review and a new configured digest.

Each term contains `id`, `name`, `description`, `synonyms`,
`name_certified:true`, `description_certified:true`, and `sha256`. Its digest is
SHA256 of UTF-8 JSON over those six content fields (excluding `sha256`), with
`sort_keys=True`, `separators=(',', ':')`, `ensure_ascii=False`, and synonyms
sorted and deduplicated. Both remote flags and the exact reviewed content must
match before NVIDIA context is used. App approval and the pinned file are
required independently of NVIDIA's certification metadata.

Set `ONTOLOGY_MODE=glossary` to use a reviewed local file. For NVIDIA, set
`ONTOLOGY_MODE=auto_ontology`, `AUTO_ONTOLOGY_URL` to the public gateway origin,
and `AUTO_ONTOLOGY_API_TOKEN` to a user API token. HTTPS is required outside
loopback; redirects are rejected. The token is sent only to that configured
origin and is never included in message metadata. `ONTOLOGY_TIMEOUT` is a total
wall-clock budget across every term, page and streamed body (default 5 seconds).

For separate organization catalogs, configure `AUTO_ONTOLOGY_CONNECTIONS` as
`{"aurora:LIVE":{"url":"http://127.0.0.1:3210","token_env":"AO_AURORA_API_TOKEN"}}`.
The token value is read from that server environment variable, never from a
request or benchmark plan. When this map is nonempty, a missing scope or token
fails closed; it does not use the global connection. The global URL/token pair
is for simple deployments sharing one deliberately reviewed catalog. Separate
NVIDIA deployments are useful when the same term name has different meanings:
the inspected upstream schema makes `(name, source)` unique. Evidence Desk's
organization and original-source checks remain required in either arrangement.

Phrase matching selects at most six approved concepts, without rewriting the
question. Valid linked chunks form an additional reciprocal-rank candidate
stream. All three streams pass the same organization, LIVE mode, ready index
and current document-version filters. A binding's document ID, version and
content hash are rechecked during retrieval. Cross-organization, deleted,
historical and changed bindings cannot promote a source. Embedding provider,
model and dimensions must match the index. The existing OpenAI index identity
remains the production default.

NVIDIA terms are context only. Returned citations retain the original chunk,
document, version, location and excerpt. Sources enriched by a term include
`semantic_context` with the review ID, file digest, source and matched terms;
the source drawer displays the reviewed concept alongside the original excerpt.
Messages record the semantic strategy and review provenance. On a configuration,
network, timeout or revision failure, chat falls back to the original retrieval
and records `unavailable_baseline_fallback`. Benchmark runs instead report a
skipped arm; they never call that fallback a successful NVIDIA run.

Application RBAC is not supplied by NVIDIA. This adapter does not assume its
admin/viewer roles enforce Evidence Desk organizations. It also does not use
`check_answerable` as an answer judge: that tool measures semantic entity coverage,
not factual correctness, citation validity or permission enforcement.

## Isolated local retrieval experiment

The adapter in `tools/ontology_adapter.py` implements Release Lab's command
protocol. It receives `{case:{id,kind,prompt,context},arm,options}` and emits
`{status,execution,output,trace,provenance,detail}`. Goldens are rejected if passed
to the adapter. It uses the prompt and explicit organization, ignores the supplied
context, and never loads expected answers. Release Lab materializes and evaluates
the independent goldens outside the SUT.

This experiment uses **real local Ollama embeddings and PostgreSQL/pgvector**,
with the same question, corpus, embedding model and retrieval code in baseline,
glossary and Auto Ontology arms. It reports `execution:live`,
`provenance.scope:retrieval_only` and `provenance.generation:extractive`.
The output is concatenated original excerpts, not a generated LLM answer.
There is no cost/token estimate or claim of generation accuracy. The returned
trace exposes the top six original chunk IDs for recall@6 and evidence checks.

Prepare PostgreSQL with pgvector and a separate benchmark database. No operation
below may target the application's ordinary database. The name must contain
`benchmark` and end in `_test`. Set `EVIDENCE_BENCHMARK_DATABASE_URL` in the
environment (not plan options). Start local Ollama with `qwen3-embedding:0.6b`.
For example, after `uv sync --frozen`:

```powershell
$env:EVIDENCE_BENCHMARK_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:5550/evidence_benchmark_test'
uv run python tools/ontology_adapter.py --prepare docs/semantic-benchmark/local
```

Preparation reads only the checked-in synthetic Markdown manuals through their
pure text extraction helper. It does not bypass or alter production upload
processing. It indexes them with their actual identity (`provider=ollama`,
`model=qwen3-embedding:0.6b`, observed dimensions), using stable original chunk
IDs. Existing incompatible benchmark data is rejected. It writes the separate
dataset, per-org glossary snapshots and adapter options under the ignored local
artifact directory. Fixture concepts and held-out prompts are checked in under
`fixtures/ontology/`; neither is rewritten by an arm.

In a Release Lab plan, use the same adapter command and `scopes_by_case` for every
arm. Baseline needs no snapshots. Glossary uses `adapter-options.json`. NVIDIA
needs a separately reviewed snapshot with `source:auto_ontology`, actual remote
term IDs/content/digests, and the same original chunk bindings; set its public
URL/token through the environment. Pin every snapshot in the plan as well as the
application options. A mock transport belongs only in contract unit tests, with
no live-performance inference. Missing NVIDIA context produces `skipped`, not a
local mock standing in for the third arm.

Primary retrieval metrics should separate the six answerable cases from the two
abstention/isolation diagnostics. Extractive retrieval is expected to return
authorized but irrelevant chunks for some unsupported questions; this does not
demonstrate an answerer's abstention ability. Track tenant leakage independently
from abstention, and do not claim improvement from a tiny synthetic corpus.
After Release Lab saves a run, `python tools/measure_retrieval.py <run-directory>
--output <metrics.json>` independently verifies the frozen artifact hashes and
computes recall@6, original-chunk evidence hits, source precision and scope
violations. Incomplete arms have null recall, rather than a fabricated zero or a
baseline result relabeled as NVIDIA.

## Validation and limits

`tests/test_ontology.py` checks the real documented HTTP envelopes using explicitly
simulated transports, total request budget, remote revision mismatch, snapshot
approval/hash/scope, exclusion of evaluator goldens, and real PostgreSQL source
binding and embedding identity. The production upload sandbox requires Linux;
Windows cannot run its Unix `resource` limits. That existing constraint is not
weakened for this feature. Run the full suite in the repository's Linux CI with
PostgreSQL/pgvector; the new integration suite also runs against native Windows
PostgreSQL with pgvector.

This integration does not demonstrate automatic ontology compilation, extraction
of facts from arbitrary PDFs, or an LLM-generated answer from NVIDIA. A local
official NVIDIA deployment can serve curated terms without cloud inference keys;
such a measurement validates the real context transport and source bridge only.
Review source drift and certification durability before operational regeneration.
NVIDIA tracks related gaps in issues [258](https://github.com/NVIDIA/auto-ontology/issues/258),
[259](https://github.com/NVIDIA/auto-ontology/issues/259) and
[260](https://github.com/NVIDIA/auto-ontology/issues/260).
