"""Official SDK transport fixtures follow documented streamed response envelopes."""
import asyncio
import json
import traceback
from contextlib import asynccontextmanager

import httpx
import pytest
from openai import AsyncOpenAI
from google import genai
from google.genai import types
from pydantic import ValidationError

from evidence.config import Settings
from evidence.providers import ModelGateway, ProviderError

ANSWER = {'text': 'Supported answer', 'chunk_ids': ['chunk-1'], 'abstain': False}


class OwnedTransport(httpx.MockTransport):
    closed = False

    async def aclose(self):
        self.closed = True
        await super().aclose()


def openai_chunk(delta, finish=None):
    return {'id': 'chatcmpl-contract', 'object': 'chat.completion.chunk', 'created': 1,
            'model': 'gpt-4.1-mini', 'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}


def gemini_chunk(text=None, finish=None, **extra):
    candidate = {'index': 0, 'content': {'role': 'model', 'parts': [] if text is None else [{'text': text}]}}
    if finish is not None:
        candidate['finishReason'] = finish
    return {'candidates': [candidate], **extra}


def streamed(events, done=False):
    content = ''.join('data: ' + json.dumps(event) + '\n\n' for event in events)
    if done:
        content += 'data: [DONE]\n\n'
    return httpx.Response(200, headers={'content-type': 'text/event-stream'}, text=content)


@asynccontextmanager
async def gateway(provider, handler, **settings):
    config = Settings(mode='LIVE', provider=provider,
        model='gpt-4.1-mini' if provider == 'openai' else 'gemini-2.5-flash',
        openai_api_key='contract-placeholder', gemini_api_key='contract-placeholder', **settings)
    transport = OwnedTransport(handler)
    if provider == 'openai':
        http = httpx.AsyncClient(transport=transport, timeout=1)
        client = AsyncOpenAI(api_key='contract-placeholder', http_client=http, max_retries=2)
        instance = ModelGateway(config, openai_client=client)
    else:
        client = genai.Client(api_key='contract-placeholder', http_options=types.HttpOptions(
            async_client_args={'transport': transport},
            retry_options=types.HttpRetryOptions(attempts=3, initial_delay=0.01, max_delay=0.02)))
        instance = ModelGateway(config, gemini_client=client)
    try:
        async with instance:
            yield instance
    finally:
        assert transport.closed


async def test_openai_actual_sdk_success_with_role_terminal_and_usage():
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        if request.url.path.endswith('/embeddings'):
            return httpx.Response(200, json={'data': [
                {'index': 1, 'embedding': [0.4, 0.5, 0.6], 'object': 'embedding'},
                {'index': 0, 'embedding': [0.1, 0.2, 0.3], 'object': 'embedding'}],
                'model': 'text-embedding-3-small', 'object': 'list',
                'usage': {'prompt_tokens': 4, 'total_tokens': 4}})
        text = json.dumps(ANSWER)
        usage = {**openai_chunk({}), 'choices': [], 'usage': {'prompt_tokens': 20, 'completion_tokens': 15, 'total_tokens': 35}}
        return streamed([openai_chunk({'role': 'assistant', 'content': ''}),
                         openai_chunk({'content': text[:20]}), openai_chunk({'content': text[20:]}),
                         openai_chunk({}, 'stop'), usage], done=True)
    async with gateway('openai', handler, embedding_dimensions=3) as model:
        assert (await model.generate('question', 'chunk-1')).model_dump() == ANSWER
        assert await model.embed(['first', 'second']) == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert requests[0]['response_format']['json_schema']['strict'] is True
    assert requests[0]['max_completion_tokens'] == 1200 and 'max_tokens' not in requests[0]
    assert requests[1]['encoding_format'] == 'float' and requests[1]['dimensions'] == 3


async def test_gemini_actual_sdk_success_with_separate_terminal():
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return streamed([gemini_chunk(), gemini_chunk(json.dumps(ANSWER)), gemini_chunk(finish='STOP'),
                         {'usageMetadata': {'promptTokenCount': 20, 'candidatesTokenCount': 15, 'totalTokenCount': 35}}])
    async with gateway('gemini', handler) as model:
        assert (await model.generate('question', 'chunk-1')).model_dump() == ANSWER
    assert requests[0]['generationConfig']['responseMimeType'] == 'application/json'
    assert requests[0]['generationConfig']['candidateCount'] == 1


@pytest.mark.parametrize('finish', ['length', 'content_filter', 'tool_calls', 'function_call', None])
async def test_openai_valid_json_does_not_override_failed_or_absent_terminal(finish):
    def handler(request):
        return streamed([openai_chunk({'content': json.dumps(ANSWER)}, finish)], done=True)
    async with gateway('openai', handler) as model:
        with pytest.raises(ProviderError, match='incomplete|terminal'):
            await model.generate('question', 'chunk-1')


@pytest.mark.parametrize('finish', ['MAX_TOKENS', 'SAFETY', 'RECITATION', 'MALFORMED_FUNCTION_CALL', 'CONTINUATION', None])
async def test_gemini_valid_json_does_not_override_failed_or_absent_terminal(finish):
    calls = []
    def handler(request):
        calls.append(request)
        return streamed([gemini_chunk(json.dumps(ANSWER), finish, continuationToken='untrusted-next-hop')])
    async with gateway('gemini', handler) as model:
        with pytest.raises(ProviderError, match='incomplete|terminal'):
            await model.generate('question', 'chunk-1')
    assert len(calls) == 1  # SDK continuation must not trigger an unbounded follow-up call.


@pytest.mark.parametrize('provider', ['openai', 'gemini'])
async def test_refusal_or_prompt_block_never_becomes_an_answer(provider):
    def handler(request):
        if provider == 'openai':
            return streamed([openai_chunk({'refusal': 'Refusal text'}, 'stop')], done=True)
        return streamed([{'promptFeedback': {'blockReason': 'SAFETY'}}])
    async with gateway(provider, handler) as model:
        with pytest.raises(ProviderError, match='declined|blocked'):
            await model.generate('question', 'context')


@pytest.mark.parametrize('provider', ['openai', 'gemini'])
async def test_structured_schema_failure_is_sanitized(provider):
    secret = 'sensitive-provider-output'
    def handler(request):
        text = json.dumps({'private': secret})
        return streamed([openai_chunk({'content': text}, 'stop')], done=True) if provider == 'openai' else streamed([gemini_chunk(text, 'STOP')])
    async with gateway(provider, handler) as model:
        with pytest.raises(ProviderError, match='invalid structured') as exc:
            await model.generate('question', 'context')
        assert secret not in ''.join(traceback.format_exception(exc.value))


@pytest.mark.parametrize('provider', ['openai', 'gemini'])
@pytest.mark.parametrize('status,expected_attempts', [(401, 1), (429, 3), (503, 3)])
async def test_sdk_retry_bounds_and_redaction(provider, status, expected_attempts):
    calls = []
    secret = 'private-key-should-not-be-exposed'
    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={'retry-after': '0'}, json={'error': {
            'message': secret, 'code': status, 'status': 'RESOURCE_EXHAUSTED' if status == 429 else 'UNAVAILABLE'}})
    async with gateway(provider, handler) as model:
        with pytest.raises(ProviderError, match='request failed') as exc:
            await model.generate('question', 'context')
        assert secret not in ''.join(traceback.format_exception(exc.value))
    assert len(calls) == expected_attempts


class SlowStream(httpx.AsyncByteStream):
    def __init__(self, first):
        self.first = first
        self.started = asyncio.Event()
        self.closed = False
    async def __aiter__(self):
        yield ('data: ' + json.dumps(self.first) + '\n\n').encode()
        self.started.set()
        await asyncio.Event().wait()
    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize('provider', ['openai', 'gemini'])
async def test_cancel_closes_active_provider_stream(provider):
    payload = openai_chunk({'content': '{'}) if provider == 'openai' else gemini_chunk('{')
    body = SlowStream(payload)
    def handler(request):
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=body)
    async with gateway(provider, handler) as model:
        task = asyncio.create_task(model.generate('question', 'context'))
        await asyncio.wait_for(body.started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert body.closed


async def test_timeout_includes_concurrency_queue():
    calls = []
    async with gateway('openai', lambda request: calls.append(request), model_timeout=0.02, model_concurrency=1) as model:
        async with model.semaphore:
            with pytest.raises(ProviderError, match='request failed'):
                await model.generate('question', 'context')
    assert not calls


@pytest.mark.parametrize('provider', ['openai', 'gemini'])
async def test_demo_never_calls_provider_even_with_keys(provider):
    model = ModelGateway(Settings(provider=provider, openai_api_key='configured', gemini_api_key='configured'))
    with pytest.raises(ProviderError, match='disabled in DEMO'):
        await model.generate('question', 'context')
    with pytest.raises(ProviderError, match='disabled in DEMO'):
        await model.embed(['text'])
    assert model.openai is None and model.gemini is None
    await model.aclose()


async def test_missing_config_never_falls_back():
    async with ModelGateway(Settings(mode='LIVE', openai_api_key='')) as model:
        with pytest.raises(ProviderError, match='incomplete'):
            await model.generate('anything', 'anything')


@pytest.mark.parametrize('data,returned_model,error', [
    ([{'index': 0, 'embedding': [0.1]}], 'text-embedding-3-small', 'dimensions'),
    ([{'index': 1, 'embedding': [0.1, 0.2, 0.3]}], 'text-embedding-3-small', 'indices'),
    ([{'index': 0, 'embedding': [0.1, 0.2, 0.3]}], 'different-model', 'model'),
    ([{'index': 0, 'embedding': [float('nan'), 0.2, 0.3]}], 'text-embedding-3-small', 'non-finite'),
])
async def test_embeddings_reject_corrupted_contract(data, returned_model, error):
    def handler(request):
        # JSON decoder accepts NaN; the adapter must reject it before pgvector storage.
        payload = {'data': [{**item, 'object': 'embedding'} for item in data], 'model': returned_model,
                   'object': 'list', 'usage': {'prompt_tokens': 1, 'total_tokens': 1}}
        return httpx.Response(200, content=json.dumps(payload).encode(), headers={'content-type': 'application/json'})
    async with gateway('openai', handler, embedding_dimensions=3) as model:
        with pytest.raises(ProviderError, match=error):
            await model.embed(['text'])


@pytest.mark.parametrize('fields', [{'model_concurrency': 0}, {'model_timeout': 0}, {'embedding_dimensions': 0},
                                    {'max_output_tokens': 0}, {'temperature': 3}])
def test_invalid_limits_fail_at_configuration(fields):
    with pytest.raises(ValidationError):
        Settings(**fields)


def test_unsupported_model_profiles_report_configuration_error():
    assert 'capability' in ' '.join(Settings(mode='LIVE', openai_api_key='set', model='o3').missing())
    assert 'capability' in ' '.join(Settings(mode='LIVE', openai_api_key='set', model='gpt-4o-2024-05-13').missing())
    assert 'dimensions' in ' '.join(Settings(mode='LIVE', openai_api_key='set', embedding_dimensions=3072).missing())


@pytest.mark.parametrize('provider', ['openai', 'gemini'])
async def test_unrequested_tool_calls_are_rejected(provider):
    def handler(request):
        if provider == 'openai':
            return streamed([openai_chunk({'tool_calls': [{'index': 0, 'id': 'tool-1', 'type': 'function',
                'function': {'name': 'read_private_document', 'arguments': '{}'}}]}, 'tool_calls')], done=True)
        return streamed([{'candidates': [{'index': 0, 'content': {'role': 'model', 'parts': [
            {'functionCall': {'name': 'read_private_document', 'args': {}}}]}, 'finishReason': 'STOP'}]}])
    async with gateway(provider, handler) as model:
        with pytest.raises(ProviderError, match='unsupported tool'):
            await model.generate('question', 'context')


async def test_gemini_thought_parts_do_not_enter_structured_answer():
    def handler(request):
        return streamed([{'candidates': [{'index': 0, 'content': {'role': 'model', 'parts': [
            {'text': 'private reasoning must not enter answer', 'thought': True},
            {'text': json.dumps(ANSWER)}]}, 'finishReason': 'STOP'}]}])
    async with gateway('gemini', handler) as model:
        assert (await model.generate('question', 'context')).model_dump() == ANSWER


async def test_schema_does_not_coerce_model_claims():
    def handler(request):
        return streamed([openai_chunk({'content': json.dumps({**ANSWER, 'abstain': 'false'})}, 'stop')], done=True)
    async with gateway('openai', handler) as model:
        with pytest.raises(ProviderError, match='invalid structured'):
            await model.generate('question', 'context')
