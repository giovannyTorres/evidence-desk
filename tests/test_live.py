"""Opt-in real calls incur provider charges; never run in ordinary CI."""
import os
import pytest
from evidence.config import Settings
from evidence.providers import ModelGateway


@pytest.mark.live
@pytest.mark.skipif(os.getenv('RUN_LIVE') != '1', reason='LIVE not authorized/configured')
async def test_live_smoke():
    config=Settings(mode='LIVE')
    assert not config.missing(), config.missing()
    async with ModelGateway(config) as gateway:
        result=await gateway.generate('What is the allowance?', '[{"chunk_id":"sample","excerpt":"The allowance is 650 MXN."}]')
        assert result.chunk_ids == ['sample'] and not result.abstain
        vectors=await gateway.embed(['synthetic smoke test'])
        assert len(vectors[0])==config.embedding_dimensions
