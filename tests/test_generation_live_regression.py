"""Opt-in model regression against the prepared isolated benchmark, not CI mocks."""
import importlib.util
import json
import os
from pathlib import Path

import pytest


@pytest.mark.live
@pytest.mark.parametrize('arm', ['baseline', 'glossary', 'auto_ontology'])
@pytest.mark.parametrize('case_id,org,expected_abstain', [
    ('ed-onto-final-cross-tenant', 'meridian', True),
    ('ed-onto-final-missing-phone', 'aurora', True),
    ('ed-onto-final-meridian-scope', 'meridian', False),
])
async def test_local_generation_regression(arm, case_id, org, expected_abstain):
    options_path = os.environ.get('EVIDENCE_REGRESSION_OPTIONS')
    if not options_path:
        pytest.skip('Set EVIDENCE_REGRESSION_OPTIONS to the prepared benchmark adapter options')
    root = Path(__file__).resolve().parents[1]
    cases = json.loads((root / 'fixtures/ontology/cases.json').read_text(encoding='utf-8'))
    descriptor = next(case for case in cases if case['id'] == case_id)
    options = json.loads(Path(options_path).read_text(encoding='utf-8'))
    spec = importlib.util.spec_from_file_location('generation_adapter_live', root / 'tools/ontology_generation_adapter.py')
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    request = {'case': {'id': case_id, 'kind': 'rag', 'prompt': descriptor['prompt']},
               'arm': arm, 'options': options}
    result = await adapter.observe_generation(request)
    assert result['status'] == 'completed', result.get('detail')
    assert result['execution'] == 'live'
    assert result['provenance']['org'] == org
    retrieved = next(event['chunk_ids'] for event in result['trace'] if event.get('event') == 'retrieval')
    # The domain loader fails closed if any retrieved ID is foreign, historical, or unavailable.
    assert len(adapter.load_authorized_sources(org, retrieved)) == len(retrieved)
    output = result['output']
    if expected_abstain:
        assert output['answer'] == adapter.ABSTENTION
        assert output['citations'] == []
    else:
        assert output['answer'] != adapter.ABSTENTION
        assert output['citations']
        assert '420' in output['answer'] and 'MXN' in output['answer'].upper()
