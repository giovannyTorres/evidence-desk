"""Explicitly opt-in LIVE evidence/abstention evaluation; does not measure semantic truth."""
import argparse
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from .config import Settings, settings
from .domain import FIXTURES, retrieve, validate_answer
from .providers import ModelGateway


async def evaluate(output: Path, split: str):
    if os.getenv('RUN_LIVE') != '1':
        raise SystemExit('Set RUN_LIVE=1 to explicitly authorize external API evaluation')
    config = Settings(mode='LIVE')
    if config.missing():
        raise SystemExit('LIVE configuration incomplete: ' + ', '.join(config.missing()))
    # retrieve uses the cached configuration; require an explicitly LIVE process.
    if settings().mode != 'LIVE':
        raise SystemExit('Set MODE=LIVE for evaluation')
    raw = (FIXTURES / 'evaluation.json').read_bytes()
    cases = [case for case in json.loads(raw) if case['split'] == split]
    gateway = ModelGateway(config)
    rows = []
    for case in cases:
        try:
            sources = await retrieve(case['question'], case['org'], gateway)
            answer = await gateway.generate(case['question'], json.dumps(sources))
            _, citations = validate_answer(answer, sources)
            passed = (not citations) if case['expected_abstention'] else any(
                c['title'] == case['expected_document'] and c['location'] == case['expected_location'] for c in citations)
            rows.append({'id': case['id'], 'evidence_check': passed, 'answer': answer.model_dump(), 'citations': citations})
        except Exception:
            rows.append({'id': case['id'], 'evidence_check': None, 'error': 'Provider, index or structured-response failure'})
    complete = [row for row in rows if row['evidence_check'] is not None]
    result = {'mode': 'LIVE', 'executed_at': datetime.now(timezone.utc).isoformat(),
              'provider': config.provider, 'model': config.model, 'embedding_model': config.embedding_model,
              'dataset_sha256': hashlib.sha256(raw).hexdigest(), 'split': split, 'total': len(rows),
              'completed': len(complete), 'passed': sum(bool(r['evidence_check']) for r in complete),
              'scope': 'Evidence location and abstention checks; not semantic accuracy', 'rows': rows}
    output.write_text(json.dumps(result, indent=2))
    print(f'Wrote {len(rows)} case outcomes to {output}; {len(complete)} completed')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--split', choices=['development', 'final'], default='final')
    args = parser.parse_args()
    asyncio.run(evaluate(args.output, args.split))


if __name__ == '__main__':
    main()
