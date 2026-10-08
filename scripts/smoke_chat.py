"""Exercise the real HTTP chat/SSE flow against a local OpenAI-compatible fixture.

No paid model provider is contacted. Run with the project's Python environment.
"""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
REPLY = 'AgentHarbor local streaming fixture passed.'


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', '0')))
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for delta, finish in [({'role': 'assistant', 'content': ''}, None), ({'content': REPLY}, None), ({}, 'stop')]:
            payload = {'id': 'harbor-fixture', 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': 'fixture', 'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}
            self.wfile.write(('data: ' + json.dumps(payload) + '\n\n').encode())
            self.wfile.flush()
        self.wfile.write(b'data: [DONE]\n\n')


def main():
    fixture = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='harbor-smoke-') as temp:
        data = Path(temp)
        env = {**os.environ, 'HARBOR_DATA_DIR': str(data / 'data'), 'HARBOR_API_PORT': str(port)}
        with (data / 'server.log').open('w', encoding='utf-8') as log:
            server = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'apps/server/main.py')], cwd=ROOT / 'apps/server', env=env, stdout=log, stderr=log)
            try:
                base = f'http://127.0.0.1:{port}'
                with httpx.Client(base_url=base, timeout=30) as client:
                    for _ in range(60):
                        try:
                            if client.get('/harbor/health').status_code == 200:
                                break
                        except httpx.ConnectError:
                            pass
                        if server.poll() is not None:
                            raise RuntimeError('Server exited during startup')
                        time.sleep(0.5)
                    result = client.post('/harbor/auth/register', json={'email': 'smoke@example.test', 'password': 'local-fixture-password', 'name': 'Smoke', 'tenant_name': 'Verification'})
                    result.raise_for_status()
                    credential = client.post('/credential/', json={'data': {'type': 'openai_credential', 'name': 'Local fixture only', 'api_key': 'local-fixture-not-a-secret', 'base_url': f'http://127.0.0.1:{fixture.server_port}/v1'}})
                    credential.raise_for_status()
                    agent = client.post('/agent/', json={'name': 'Fixture Agent', 'system_prompt': 'Reply briefly. Do not call tools.'})
                    agent.raise_for_status()
                    aid = agent.json()['agent_id']
                    session = client.post('/sessions/', json={'agent_id': aid, 'name': 'HTTP smoke', 'chat_model_config': {'type': 'openai_credential', 'credential_id': credential.json()['credential_id'], 'model': 'fixture', 'parameters': {}}})
                    session.raise_for_status()
                    sid = session.json()['session_id']
                    ready = threading.Event()
                    def observe():
                        with httpx.Client(base_url=base, cookies=client.cookies, timeout=30) as stream_client:
                            with stream_client.stream('GET', f'/sessions/{sid}/stream', params={'agent_id': aid}) as stream:
                                stream.raise_for_status()
                                ready.set()
                                for line in stream.iter_lines():
                                    if REPLY in line:
                                        return True
                        return False
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        observed = pool.submit(observe)
                        if not ready.wait(15):
                            raise RuntimeError('SSE subscription did not open')
                        triggered = client.post('/chat/', json={'agent_id': aid, 'session_id': sid, 'input': {'name': 'user', 'role': 'user', 'content': [{'type': 'text', 'text': 'Hello'}]}})
                        triggered.raise_for_status()
                        assert observed.result(timeout=40), 'No streamed assistant output'
                    for _ in range(40):
                        messages = client.get(f'/sessions/{sid}/messages', params={'agent_id': aid})
                        messages.raise_for_status()
                        if REPLY in messages.text and not messages.json().get('is_running'):
                            break
                        time.sleep(0.25)
                    assert REPLY in messages.text, 'Assistant output was not persisted'
                    print(json.dumps({'http_registration': True, 'credential': True, 'agent': True, 'session': True, 'chat_trigger': True, 'sse_reply': True, 'message_persistence': True, 'provider': 'local fixture; no real model call'}))
            except Exception:
                log.flush()
                print((data / 'server.log').read_text(encoding='utf-8')[-7000:], file=sys.stderr)
                raise
            finally:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
                fixture.shutdown()


if __name__ == '__main__':
    main()
