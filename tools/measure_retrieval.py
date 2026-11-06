"""Measure original-chunk retrieval against frozen goldens outside the adapter."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measure(directory: Path) -> dict:
    manifest_path = directory / 'manifest.json'
    if digest(manifest_path) != (directory / 'manifest.sha256').read_text().strip():
        raise ValueError('Manifest digest mismatch')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for name, expected in manifest['artifacts'].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or digest(path) != expected:
            raise ValueError('Frozen experiment artifact mismatch')
    cases = json.loads((directory / 'inputs/dataset.json').read_text(encoding='utf-8'))
    answerable = [case for case in cases if not case['expected']['abstain']]
    unsupported = [case for case in cases if case['expected']['abstain']]
    arms = {}
    for arm in ('baseline', 'glossary', 'auto_ontology'):
        trace = json.loads((directory / arm / 'trace.json').read_text(encoding='utf-8'))
        observations = {row['case_id']: row['observation'] for row in trace}
        completed = {key: value for key, value in observations.items() if value['status'] == 'completed'}
        recalls, precisions = [], []
        exact = strict_sets = 0
        violations = []
        for case in cases:
            observation = completed.get(case['id'])
            if not observation:
                continue
            returned = observation['output']['citations']
            event = next(event for event in observation['trace'] if event.get('event') == 'retrieval')
            if returned != event['chunk_ids'] or len(returned) > 6:
                raise ValueError('Output and original-chunk retrieval trace disagree')
            allowed = set(case['expected']['allowed_citations'])
            violations.extend({'case_id': case['id'], 'chunk_id': value} for value in returned if value not in allowed)
            required = set(case['expected']['required_citations'])
            if required:
                hit = required & set(returned)
                recalls.append(len(hit) / len(required))
                precisions.append(len(hit) / len(returned) if returned else 0)
                exact += required <= set(returned)
                strict_sets += required == set(returned)
        complete_answerable = bool(answerable) and len(recalls) == len(answerable)
        arms[arm] = {
            'completed': len(completed),
            'skipped': sum(value['status'] == 'skipped' for value in observations.values()),
            'errors': sum(value['status'] == 'error' for value in observations.values()),
            'answerable_cases': len(answerable), 'answerable_completed': len(recalls),
            'recall_at_6': sum(recalls) / len(answerable) if complete_answerable else None,
            'relevant_chunk_precision_at_6': sum(precisions) / len(answerable) if complete_answerable else None,
            'all_required_exact_chunk_ids_found': exact,
            'strict_exact_chunk_set_matches': strict_sets,
            'unauthorized_chunk_count': len(violations), 'scope_violations': violations,
            'abstention_diagnostic_cases': len(unsupported),
            'abstention_diagnostics_returning_no_sources': sum(
                case['id'] in completed and not completed[case['id']]['output']['citations'] for case in unsupported),
            'verified_nvidia_get_requests': sum(int(value.get('provenance', {}).get('ontology_http_requests', '0'))
                                              for value in completed.values()),
        }
    return {'scope': 'retrieval_only', 'generation': 'extractive',
            'dataset_sha256': digest(directory / 'inputs/dataset.json'), 'arms': arms,
            'limits': ['Small synthetic corpus; no generated-answer quality measurement',
                       'Curated NVIDIA terms; automatic ontology compilation was not executed',
                       'Command wall latency includes process startup; not model-only latency',
                       'Abstention diagnostics are separate from answerable-case recall']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    value = measure(args.directory.resolve())
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    if args.output:
        args.output.write_bytes(raw)
        args.output.with_suffix(args.output.suffix + '.sha256').write_text(hashlib.sha256(raw).hexdigest() + '\n')
    else:
        print(raw.decode(), end='')


if __name__ == '__main__':
    main()
