"""Flush SSE headers with an initial comment for native streaming clients."""
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SSEHandshake:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope['type'] != 'http' or scope['method'] != 'GET':
            await self.app(scope, receive, send)
            return

        async def send_with_handshake(message: Message):
            if message['type'] == 'http.response.start' and message['status'] == 200:
                headers = message.get('headers', [])
                content_type = next((v for k, v in headers if k.lower() == b'content-type'), b'')
                if content_type.split(b';', 1)[0].strip().lower() == b'text/event-stream':
                    # iOS may not deliver the fetch Response until body bytes arrive.
                    # Idle upstream sessions otherwise send their first heartbeat at
                    # 30 seconds, after the mobile client's 20-second timeout.
                    await send({**message, 'headers': [
                        (k, v) for k, v in headers if k.lower() != b'content-length'
                    ]})
                    await send({'type': 'http.response.body', 'body': b': connected\n\n', 'more_body': True})
                    return
            await send(message)

        await self.app(scope, receive, send_with_handshake)
