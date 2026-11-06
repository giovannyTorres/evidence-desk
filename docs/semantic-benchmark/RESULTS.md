# Local semantic retrieval experiment — 2026-11-06

All three arms completed the same eight frozen synthetic cases against the same
PostgreSQL corpus and real local Ollama embeddings. The NVIDIA arm used the
official upstream application and public HTTP gateway, with separate Aurora and
Meridian catalogs and tokens. It completed **14 real GET requests**, with no
simulated transport, skipped observations or errors.

| Arm | Completed | Recall@6, six answerable cases | Exact required chunk IDs found | Unauthorized chunks |
|---|---:|---:|---:|---:|
| Baseline hybrid retrieval | 8/8 | 1.00 | 6/6 | 0 |
| Reviewed local glossary | 8/8 | 1.00 | 6/6 | 0 |
| NVIDIA Auto Ontology context | 8/8 | 1.00 | 6/6 | 0 |

There was **no measured improvement or regression** in required evidence recall
or the paired RAG checks. All three arms returned additional authorized chunks;
mean relevant-chunk precision was 0.2222 and strict exact-set matches were 0/6.
The corpus is small and baseline recall is already at its ceiling.

The adapter returns original excerpts and citations, without generating an LLM
answer. Both unsupported/abstention diagnostics returned sources in every arm,
so all arms passed 6/8 overall RAG checks and the strict experiment gate rejected
them. Retrieval recall does not establish abstention or generated-answer quality.
NVIDIA served manually reviewed synthetic terms; automatic ontology compilation
and NVIDIA inference were not executed. These results do not establish a product
release approval or a general accuracy gain.

The report also records command wall time, which includes Python startup,
application execution and local machine load. Eight sequential cases are not
enough to claim a causal latency improvement. Usage tokens and costs remain null.

## Reproduction identity

- Evidence Desk measured commit: `a847e7b47a3bb46b1ed9044f8173592de2b60857`.
- Official NVIDIA upstream commit: `c4495670947eb7b4616f0dd9900e5ced2a48ca1e`.
- Embeddings: Ollama `qwen3-embedding:0.6b`, 1024 dimensions, model digest
  `ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`.
- Frozen dataset SHA256:
  `1134f002ae58d48ab44c2c77d3d40f4adb823fb0bd1897a168006aa1361f855b`.
- Measured source-file manifest SHA256:
  `69430099b10eae4acfc84506ed867d5c7b6fc25b41901505234bb393b1072ac2`.
- Experiment manifest SHA256:
  `84155bdfd4db26253319f3d759ffe15ece54a21e71b75a53654258a59c98c41e`.
- Independent retrieval metrics SHA256:
  `3d4d567fb9b1c40ec0da49f04fdc50dfef894f82907f1617080c40af0d077303`.

The workspace-local archive is `verification/evidence-desk/run-20261106-scoped`
under the parent outputs directory. It contains frozen inputs, per-arm imports
and traces, the report, manifest, and independent retrieval metrics. The Release
Lab `--verify` command and `tools/measure_retrieval.py` both verified the saved
artifact hashes. Reproduction commands and trust contracts are documented in
[the integration guide](../auto-ontology.md).
