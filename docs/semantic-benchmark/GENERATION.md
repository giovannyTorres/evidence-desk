# Complementary local generation experiment

`tools/ontology_generation_adapter.py` complements the retrieval-only experiment.
It uses the same eight frozen cases and goldens, the same baseline/glossary/Auto
Ontology retrieval caller, and the same original PostgreSQL corpus. The existing
retrieval results and their identities remain separate.

The adapter calls `observe` for real retrieval, then reloads its returned chunk
IDs through the product's `source_rows(org, LIVE)` filter. Missing, foreign,
DEMO, historical or non-ready sources are rejected. Reviewed semantic metadata
is reconstructed only from the already verified pinned snapshot and matching
original source bindings. Neither the evaluator's context nor expected answers
are passed to the model. The command protocol rejects goldens through the
retrieval caller before inference.

Generation uses loopback Ollama `qwen3.5:4b` with `temperature=0`, `seed=42`,
`num_predict=1600`, `think=false` and non-streaming `/api/chat`. Every arm uses the
same fixed profile. The product's exact `SYSTEM`, strict `Answer` JSON schema,
and `validate_answer` are reused; production OpenAI/Gemini providers are
unchanged. Schema transport follows the official
[Ollama chat API](https://docs.ollama.com/api/chat) and
[structured-output contract](https://docs.ollama.com/capabilities/structured-outputs).

The response must identify the requested model, finish with `done=true` and
`done_reason=stop`, and contain an assistant message with a valid strict Answer.
Missing or truncated terminal states, tool calls, wrong model/role, malformed
schema, duplicate JSON keys and invalid evidence references produce an error
observation with no output. Thinking content is never used or saved as an answer.
Cited sources are reloaded after inference and their original content/version
identity must still match. Empty source sets take the product's evidence-absence
abstention path without invoking a model. No provider body or invalid generated
answer is reflected in error details.

Completed real calls report `execution:live`,
`provenance.scope:domain_rag_generation`, and `generation:ollama`. Domain source
filtering is exercised directly; the adapter does **not** exercise the app's
HTTP session authentication. NVIDIA supplies reviewed context through its real
public GET API. NVIDIA discovery, automatic ontology generation and NVIDIA
text-to-SQL inference are outside this experiment. Test injections are always
`transport_mock`, including when only the retrieval or source loader is replaced.

Use a separate Release Lab plan and destination. Point all three arm commands at
the generation adapter, retain the original case scopes and snapshot options,
and keep the same dataset SHA256:
`1134f002ae58d48ab44c2c77d3d40f4adb823fb0bd1897a168006aa1361f855b`.
Set `EVIDENCE_BENCHMARK_DATABASE_URL`, the scoped NVIDIA connections/token
environment references, and optionally `EVIDENCE_EVAL_OLLAMA_URL` (loopback only).
The adapter has a 180-second total model-response budget; the enclosing command
budget should also cover retrieval and process startup. It never reads secrets
from plan options.

Keep the local generation model digest, embedding model digest, source commit,
snapshot hashes and fixed profile in the plan provenance. Usage tokens, when
both native counts are present, are the model's prompt plus completion tokens
only; embedding usage and cost are not inferred. Command wall latency remains
distinct from model-only runtime. No generated-answer performance result is
claimed by the transport tests or the retrieval-only report.


## Opt-in abstention regression

The production system instruction asks the model to distinguish related evidence
from evidence for the specific requested organization and policy. This is a
prompt change, not a semantic entailment or authorization guarantee. A mocked
test covers the response contract; it does not establish model behavior.

With the separately prepared benchmark database, local Ollama embedding and
generation models, and real scoped NVIDIA gateways configured as above, set
`EVIDENCE_REGRESSION_OPTIONS` to an adapter-options JSON containing the
scoped snapshots appropriate to each arm. The baseline needs no snapshots;
glossary and Auto Ontology use different snapshot sources, so run each arm
with its corresponding options file via pytest's `-k` filter. For example:

```text
EVIDENCE_REGRESSION_OPTIONS=<baseline-options.json> uv run pytest -q -m live tests/test_generation_live_regression.py -k baseline
EVIDENCE_REGRESSION_OPTIONS=<glossary-options.json> uv run pytest -q -m live tests/test_generation_live_regression.py -k glossary
EVIDENCE_REGRESSION_OPTIONS=<auto-options.json> uv run pytest -q -m live tests/test_generation_live_regression.py -k auto_ontology
```

The tests check the cross-organization and missing-phone abstentions and a
positive Meridian answer, using real retrieval and generation. Missing gateways,
invalid snapshots or unexpected model output fail the run; they are not
reported as passes. This test checks authorized retrieved IDs using the domain
filter, but does not exercise HTTP login or establish general factual grounding.
