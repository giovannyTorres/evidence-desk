import json
import httpx
import pytest
from openai import AsyncOpenAI
from google import genai
from google.genai import types
from evidence.config import Settings
from evidence.providers import ModelGateway

ANSWER = {'text':'Supported answer', 'chunk_ids':['chunk-1'], 'abstain':False}


async def test_openai_actual_sdk_mock_transport():
    requests=[]
    def handler(request):
        requests.append(json.loads(request.content))
        if request.url.path.endswith('/embeddings'):
            return httpx.Response(200,json={'data':[{'index':0,'embedding':[0.1,0.2,0.3],'object':'embedding'}], 'model':'text-embedding-3-small','object':'list','usage':{'prompt_tokens':2,'total_tokens':2}})
        payload={'id':'test','object':'chat.completion.chunk','created':1,'model':'gpt-4.1-mini','choices':[{'index':0,'delta':{'content':json.dumps(ANSWER)},'finish_reason':None}]}
        return httpx.Response(200,headers={'content-type':'text/event-stream'},text='data: '+json.dumps(payload)+'\n\ndata: [DONE]\n\n')
    client=AsyncOpenAI(api_key='contract-placeholder',http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),max_retries=0)
    gateway=ModelGateway(Settings(mode='LIVE',openai_api_key='contract-placeholder',embedding_dimensions=3),openai_client=client)
    result=await gateway.generate('question','chunk-1')
    assert result.text == ANSWER['text']
    assert await gateway.embed(['text']) == [[0.1,0.2,0.3]]
    assert requests[0]['response_format']['json_schema']['strict'] is True
    await client.close()


async def test_gemini_actual_sdk_mock_transport():
    requests=[]
    def handler(request):
        requests.append(json.loads(request.content))
        payload={'candidates':[{'content':{'role':'model','parts':[{'text':json.dumps(ANSWER)}]},'finishReason':'STOP'}]}
        return httpx.Response(200,headers={'content-type':'text/event-stream'},text='data: '+json.dumps(payload)+'\n\n')
    gemini=genai.Client(api_key='contract-placeholder',http_options=types.HttpOptions(async_client_args={'transport':httpx.MockTransport(handler)}))
    gateway=ModelGateway(Settings(mode='LIVE',provider='gemini',model='gemini-2.5-flash',openai_api_key='contract-placeholder',gemini_api_key='contract-placeholder'),gemini_client=gemini)
    result=await gateway.generate('question','chunk-1')
    assert result.text == ANSWER['text']
    assert requests[0]['generationConfig']['responseMimeType']=='application/json'
    await gemini.aio.aclose()


async def test_missing_config_never_falls_back():
    gateway=ModelGateway(Settings(mode='LIVE',openai_api_key=''))
    with pytest.raises(ValueError,match='incomplete'):
        await gateway.generate('anything','anything')


async def test_embedding_dimensions_rejected():
    def handler(request):
        return httpx.Response(200,json={'data':[{'index':0,'embedding':[0.1],'object':'embedding'}], 'model':'x','object':'list','usage':{'prompt_tokens':1,'total_tokens':1}})
    client=AsyncOpenAI(api_key='placeholder',http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    gateway=ModelGateway(Settings(openai_api_key='placeholder',embedding_dimensions=3),openai_client=client)
    with pytest.raises(ValueError,match='dimensions'):
        await gateway.embed(['x'])
