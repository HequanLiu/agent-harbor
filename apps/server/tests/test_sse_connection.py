"""Exercise idle SSE over a real socket (buffered clients hide first-byte delays)."""
import asyncio
import socket
import threading
import time

import httpx
import uvicorn

from harbor.app import create_harbor_app
from harbor.sse import SSEHandshake


def test_idle_session_delivers_first_frame_without_waiting_for_heartbeat(tmp_path):
    app = create_harbor_app(tmp_path)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, 'Fixture server did not start'
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=2) as client:
            response = client.post('/harbor/auth/register', json={
                'email': 'sse@example.test', 'password': 'local-sse-test-password',
                'name': 'SSE test', 'tenant_name': 'SSE test',
            })
            response.raise_for_status()
            response = client.post('/harbor/auth/mobile/login', json={
                'email': 'sse@example.test', 'password': 'local-sse-test-password',
            })
            response.raise_for_status()
            client.cookies.clear()
            client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
            response = client.post('/agent/', json={'name': 'Idle SSE test'})
            response.raise_for_status()
            agent = response.json()['agent_id']
            response = client.post('/sessions/', json={'agent_id': agent})
            response.raise_for_status()
            session = response.json()['session_id']
            path = f'/sessions/{session}/stream?agent_id={agent}'
            started = time.monotonic()
            with client.stream('GET', path) as stream:
                assert stream.status_code == 200
                assert stream.headers['content-type'].startswith('text/event-stream')
                first = next(stream.iter_bytes())
                assert first.startswith(b':') and b'\n\n' in first
                assert time.monotonic() - started < 2
            # Reconnection to the same still-idle session must also receive bytes.
            with client.stream('GET', path) as stream:
                assert next(stream.iter_bytes()).startswith(b':')
            # Authentication failures must remain normal JSON responses.
            client.headers.pop('Authorization')
            denied = client.get(path)
            assert denied.status_code == 401
            assert 'detail' in denied.json()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive(), 'Fixture server did not stop'


def test_handshake_preserves_event_chunks_and_stream_completion():
    async def check():
        chunks = [
            {'type': 'http.response.start', 'status': 200, 'headers': [
                (b'content-type', b'text/event-stream; charset=utf-8'),
                (b'cache-control', b'no-cache'),
            ]},
            {'type': 'http.response.body', 'body': b'data: {"type":"REPLY_', 'more_body': True},
            {'type': 'http.response.body', 'body': b'END"}\n\n', 'more_body': True},
            {'type': 'http.response.body', 'body': b'', 'more_body': False},
        ]
        sent = []

        async def upstream(scope, receive, send):
            for chunk in chunks:
                await send(chunk)

        async def send(message):
            sent.append(message)

        await SSEHandshake(upstream)({'type': 'http', 'method': 'GET'}, None, send)
        assert sent[0] == chunks[0]
        assert sent[1]['body'] == b': connected\n\n'
        assert sent[1]['more_body'] is True
        assert sent[2:] == chunks[1:]

    asyncio.run(check())
