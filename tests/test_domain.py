import json
from pathlib import Path
import pytest
from evidence.domain import extract, validate_answer
from evidence.providers import Answer


def test_extraction_sections():
    assert extract('manual.md', b'# Manual\n## Travel\nTen days.')[0] == ('Travel', 'Ten days.')


@pytest.mark.parametrize('name,data', [('x.exe', b'abcd'), ('x.pdf', b'not pdf'), ('x.txt', b'\x00binary'), ('x.txt', b'')])
def test_invalid_files(name, data):
    with pytest.raises(ValueError):
        extract(name, data)


def test_fabricated_reference_blocked():
    with pytest.raises(ValueError):
        validate_answer(Answer(text='unsupported', chunk_ids=['secret-id'], abstain=False), [])


def test_no_citations_abstains():
    answer, citations = validate_answer(Answer(text='invented', chunk_ids=[], abstain=False), [])
    assert 'enough evidence' in answer and citations == []


def test_evaluation_inventory():
    cases = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/evaluation.json').read_text())
    assert len(cases) >= 40
    assert any(c['kind'] == 'isolation' for c in cases)
    assert any(c['expected_abstention'] for c in cases)
    assert all(c['model_metrics'] is None for c in cases)
