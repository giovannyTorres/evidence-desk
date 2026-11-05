"""Bound request bytes before multipart parsing or disk spooling."""
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes: int = 6 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        try:
            declared = int(headers.get(b'content-length', b'0'))
        except ValueError:
            return await JSONResponse({'detail': 'Invalid content length'}, 400)(scope, receive, send)
        if declared < 0 or declared > self.max_bytes:
            return await JSONResponse({'detail': 'Request exceeds 6 MiB limit'}, 413)(scope, receive, send)
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get('body', b''))
            if consumed > self.max_bytes:
                raise HTTPException(413, 'Request exceeds 6 MiB limit')
            return message

        await self.app(scope, bounded_receive, send)
