import asyncio
import json
import signal
from evidence.domain import process_one
from evidence.seed import seed
from evidence.telemetry import configure_tracing


async def main():
    configure_tracing()
    seed()
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    while not stop.is_set():
        try:
            if not await process_one():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=1)
                except TimeoutError:
                    pass
        except Exception:
            print(json.dumps({'event': 'worker_retry', 'error': 'Database unavailable'}), flush=True)
            await asyncio.sleep(2)


if __name__ == '__main__':
    asyncio.run(main())
