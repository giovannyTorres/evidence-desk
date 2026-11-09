"""Regression checks for the curated DEMO walkthrough data (synthetic fixtures only)."""
import hashlib
import json

from evidence.domain import FIXTURES, scenarios
from evidence.seed import demo_fixture_bytes


def _ask(client, scenario_id):
    cid = client.post('/api/conversations', json={}).json()['id']
    result = client.post(f'/api/conversations/{cid}/messages', json={'scenario_id': scenario_id})
    assert result.status_code == 200 and 'event: done' in result.text
    return client.get(f'/api/conversations/{cid}').json()['messages'][-1]


def test_demo_fixture_hashes_survive_windows_line_endings(tmp_path):
    # Git for Windows commonly checks text files out as CRLF; the seeded DEMO bytes must stay identical.
    manual_hashes = set()
    for manual in sorted((FIXTURES / 'manuals').glob('*/*.md')):
        original = manual.read_bytes()
        assert b'\r\n' not in original, f'{manual} must be stored with LF line endings'
        crlf = tmp_path / manual.name
        crlf.write_bytes(original.replace(b'\n', b'\r\n'))
        expected = hashlib.sha256(original).hexdigest()
        assert hashlib.sha256(demo_fixture_bytes(crlf)).hexdigest() == expected
        manual_hashes.add(expected)
    bound = {s['evidence_hash'] for s in scenarios() if s['document'] is not None}
    assert bound <= manual_hashes, 'Every DEMO answer must be bound to a shipped synthetic manual'


def test_demo_abstention_examples_are_reviewed_unanswerable_questions():
    # The no-evidence example must not be answerable from the corpus (eval-024 expects a cited answer
    # for the payment-date question, so it cannot also be the abstention example).
    evaluation = json.loads((FIXTURES / 'evaluation.json').read_text(encoding='utf-8'))
    unanswerable = {e['question'] for e in evaluation if e['expected_abstention'] and e['kind'] == 'unanswerable'}
    answerable = {e['question'] for e in evaluation if not e['expected_abstention']}
    abstentions = [s for s in scenarios() if s['document'] is None]
    assert abstentions
    for scenario in abstentions:
        assert scenario['question'] in unanswerable and scenario['question'] not in answerable


def test_demo_examples_are_answered_only_inside_their_organization(client):
    # Aurora cannot obtain Meridian's example, and Meridian cannot obtain Aurora's.
    foreign = _ask(client, 'meridian-meals')
    assert 'cannot support' in foreign['content'] and foreign['citations'] == []
    assert '420' not in foreign['content']
    assert client.post('/api/auth/login', json={'email': 'analyst@meridian.example',
                                                 'password': 'demo-evidence'}).status_code == 200
    own = _ask(client, 'meridian-meals')
    assert '420 MXN' in own['content']
    assert own['citations'] and {c['title'] for c in own['citations']} == {'Meridian Travel Handbook'}
    excerpt = client.get('/api/sources/' + own['citations'][0]['chunk_id']).json()['excerpt']
    assert '420 MXN' in excerpt
    aurora_example = _ask(client, 'travel-meals')
    assert 'cannot support' in aurora_example['content'] and aurora_example['citations'] == []
    assert '650' not in aurora_example['content']
