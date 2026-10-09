"""Mobile Web E2E against an isolated backend and local model; no paid calls.
Export Web with EXPO_PUBLIC_API_URL=http://127.0.0.1:18017/ first.
Set HARBOR_PYTHON if this worktree uses another checkout's Python environment.
Requires Playwright (Edge) and httpx in the invoking Python environment.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import re
import subprocess
import socket
import tempfile
import threading
import time

import httpx
from playwright.sync_api import sync_playwright, expect
from smoke_chat import Fixture, REPLY, ROOT


MARKDOWN_REPLY = """## Markdown preview

**Bold result** and *italic text* with `inline_code`.

- First item
- Second item

> Quoted result

```python
print("markdown works")
long_value = "abcdefghijklmnopqrstuvwxyz_abcdefghijklmnopqrstuvwxyz_abcdefghijklmnopqrstuvwxyz"
```

| Feature | Status |
| --- | --- |
| Markdown | Ready |

[Documentation](https://example.com/docs)
"""


class SlowFixture(Fixture):
    def do_POST(self):
        payload = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        request = json.loads(payload)
        messages = request.get('messages', [])
        last_user = max((i for i, m in enumerate(messages) if m.get('role') == 'user'), default=-1)
        user_text = json.dumps(messages[last_user].get('content', '')) if last_user >= 0 else ''
        confirmation = next((kind for kind in ('ONCE', 'DENY', 'RULE') if f'CONFIRM_{kind}' in user_text), None)
        if confirmation:
            output = Path(self.server.confirm_dir) / f'{confirmation.lower()}.txt'
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            if any(m.get('role') == 'tool' for m in messages[last_user+1:]):
                delta = {'content': f'Confirmation {confirmation} completed.'}
                reason = 'stop'
            else:
                delta = {'tool_calls': [{'index': 0, 'id': f'call-{confirmation}', 'type': 'function', 'function': {'name': 'Write', 'arguments': json.dumps({'file_path': str(output), 'content': 'mobile confirmation fixture'})}}]}
                reason = 'tool_calls'
            for part, finish in ((delta, None), ({}, reason)):
                event = {'id': 'fixture', 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model':'fixture', 'choices':[{'index':0, 'delta':part, 'finish_reason':finish}]}
                self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
                self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n')
            return
        slow = b'STOP_FIXTURE'  in payload or b'GAP_FIXTURE' in payload
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        markdown = not slow and b'MARKDOWN_FIXTURE' in payload
        chunks = [('Working... ' if slow else REPLY, None)]
        if markdown:
            chunks = [(MARKDOWN_REPLY[i:i+18], None) for i in range(0, len(MARKDOWN_REPLY), 18)]
        if slow:
            chunks += [('more ', None)] * 30
        chunks += [('', 'stop')]
        try:
            for text, finish in chunks:
                data = {'id': 'fixture', 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': 'fixture', 'choices': [{'index': 0, 'delta': {'content': text}, 'finish_reason': finish}]}
                self.wfile.write(('data: ' + json.dumps(data) + '\n\n').encode())
                self.wfile.flush()
                if slow or markdown:
                    time.sleep(0.3 if slow else 0.06)
            self.wfile.write(b'data: [DONE]\n\n')
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


class Web(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if not Path(self.translate_path(self.path)).is_file():
            self.path = '/index.html'
        super().do_GET()


def main():
    # Never register fixture data against an unrelated server using this port.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 18017))
    python = os.getenv('HARBOR_PYTHON', str(ROOT / '.venv/Scripts/python.exe'))
    artifacts = ROOT / '.runtime/mobile-smoke'
    artifacts.mkdir(parents=True, exist_ok=True)
    fixture = ThreadingHTTPServer(('127.0.0.1', 0), SlowFixture)
    web = ThreadingHTTPServer(('127.0.0.1', 18018), partial(Web, directory=str(ROOT / 'apps/mobile/dist')))
    for service in (fixture, web):
        threading.Thread(target=service.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory(prefix='harbor-mobile-') as temp:
        fixture.confirm_dir = temp
        env = {**os.environ, 'HARBOR_DATA_DIR': temp, 'HARBOR_API_PORT': '18017', 'HARBOR_HOST': '127.0.0.1', 'HARBOR_ALLOW_REGISTRATION': 'true', 'HARBOR_ALLOWED_ORIGINS': 'http://127.0.0.1:18018'}
        with (artifacts / 'server.log').open('w', encoding='utf-8') as log:
            server = subprocess.Popen([python, '-X', 'utf8', str(ROOT / 'apps/server/main.py')], cwd=ROOT / 'apps/server', env=env, stdout=log, stderr=log)
            try:
                with httpx.Client(base_url='http://127.0.0.1:18017', timeout=30) as client:
                    for _ in range(80):
                        if server.poll() is not None:
                            raise RuntimeError('Fixture server exited; see .runtime/mobile-smoke/server.log')
                        try:
                            if client.get('/harbor/health').status_code == 200:
                                break
                        except httpx.ConnectError:
                            pass
                        time.sleep(0.5)
                    def post(url, body):
                        response = client.post(url, json=body)
                        response.raise_for_status()
                        return response.json()
                    post('/harbor/auth/register', {'email': 'mobile@example.test', 'password': 'local-fixture-password', 'name': 'Mobile', 'tenant_name': 'Mobile fixture'})
                    credential = post('/credential/', {'data': {'type': 'openai_credential', 'name': 'Local fixture', 'api_key': 'fixture-not-a-real-secret', 'base_url': f'http://127.0.0.1:{fixture.server_port}/v1'}})
                    agent = post('/agent/', {'name': 'Fixture Agent', 'system_prompt': 'Reply briefly, no tools.'})
                    post('/sessions/', {'agent_id': agent['agent_id'], 'name': 'Earlier chat', 'chat_model_config': {'type': 'openai_credential', 'credential_id': credential['credential_id'], 'model': 'fixture', 'parameters': {}}})
                    choices = client.get('/mobile/credentials')
                    choices.raise_for_status()
                    assert set(choices.json()['credentials'][0]) == {'id', 'name', 'type'}
                    with sync_playwright() as p:
                        browser = p.chromium.launch(channel='msedge', headless=True)
                        page = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
                        page.set_default_timeout(20000)
                        def reopen_chat():
                            page.get_by_role('button', name='返回会话列表').click()
                            page.get_by_role('button', name=re.compile('^打开对话 ')).first.click()
                        errors = []
                        confirmation_requests = []
                        def track_confirmation(request):
                            if request.method == 'POST' and request.url.endswith('/chat/'):
                                data = request.post_data_json
                                if data.get('input', {}).get('type') == 'USER_CONFIRM_RESULT':
                                    confirmation_requests.append(data['input'])
                        page.on('request', track_confirmation)
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        try:
                            page.goto('http://127.0.0.1:18018')
                            expect(page.get_by_role('button', name='登录', exact=True)).to_be_visible()
                            page.screenshot(path=str(artifacts / 'login.png'), full_page=True)
                            page.get_by_label('邮箱', exact=True).fill('mobile@example.test')
                            page.get_by_label('密码', exact=True).fill('wrong-password')
                            page.get_by_role('button', name='显示密码', exact=True).click()
                            expect(page.get_by_label('密码', exact=True)).not_to_have_attribute('type', 'password')
                            page.get_by_role('checkbox', name='记住密码').click()
                            page.get_by_role('button', name='登录', exact=True).click()
                            expect(page.get_by_role('alert')).to_be_visible()
                            page.reload()
                            expect(page.get_by_label('密码', exact=True)).to_be_editable()
                            expect(page.get_by_label('密码', exact=True)).to_have_value('')
                            expect(page.get_by_role('checkbox', name='记住密码')).not_to_be_checked()
                            page.get_by_label('邮箱', exact=True).fill('mobile@example.test')
                            page.get_by_role('checkbox', name='记住密码').click()
                            page.get_by_label('密码', exact=True).fill('local-fixture-password')
                            page.get_by_role('button', name='登录', exact=True).click()
                            expect(page.get_by_label('消息', exact=True)).to_be_visible()
                            expect(page.get_by_text('fixture', exact=True)).to_have_count(0)
                            expect(page.get_by_label('已连接', exact=True)).to_be_visible()
                            page.screenshot(path=str(artifacts / 'default-chat-home.png'), full_page=True)
                            page.get_by_role('button', name='返回会话列表').click()
                            expect(page.get_by_role('button', name='打开对话 Earlier chat')).to_be_visible()
                            page.screenshot(path=str(artifacts / 'home.png'), full_page=True)
                            page.get_by_role('button', name='＋ 新建对话').click()
                            expect(page.get_by_label('消息', exact=True)).to_be_visible()
                            expect(page.get_by_label('模型名称')).to_have_count(0)
                            previous_url = page.url
                            page.get_by_role('button', name='新建对话', exact=True).evaluate('(button) => { button.click(); button.click(); }')
                            page.wait_for_url(lambda url: str(url) != previous_url)
                            expect(page.get_by_label('消息', exact=True)).to_have_value('')
                            expect(page.get_by_text('让想法有个开始', exact=True)).to_be_visible()
                            expect(page.get_by_text('fixture', exact=True)).to_have_count(0)
                            created_sessions = client.get('/sessions/', params={'agent_id':agent['agent_id']}).json()['sessions']
                            assert len(created_sessions) == 3, 'New chat created twice or missing'
                            assert all(item['session']['config']['chat_model_config']['model'] == 'fixture' for item in created_sessions)
                            page.screenshot(path=str(artifacts / 'new-chat.png'), full_page=True)
                            expect(page.get_by_label('已连接', exact=True)).to_be_visible()
                            page.get_by_label('消息', exact=True).fill('Hello mobile')
                            page.get_by_role('button', name='发送消息', exact=True).click()
                            expect(page.get_by_text(REPLY, exact=True)).to_be_visible()
                            expect(page.get_by_role('button', name='发送消息', exact=True)).to_be_visible()
                            page.screenshot(path=str(artifacts / 'chat.png'), full_page=True)
                            reopen_chat()
                            expect(page.get_by_text(REPLY, exact=True)).to_be_visible()
                            expect(page.get_by_text('Hello mobile', exact=True).and_(page.locator(':visible'))).to_have_count(1)
                            page.get_by_label('消息', exact=True).fill('**MARKDOWN_FIXTURE**')
                            page.get_by_role('button', name='发送消息', exact=True).click()
                            expect(page.get_by_text('Markdown preview', exact=True)).to_be_visible()
                            expect(page.get_by_role('button', name='停止生成', exact=True)).to_be_visible()
                            expect(page.get_by_role('button', name='发送消息', exact=True)).to_be_visible()
                            expect(page.get_by_text('Bold result', exact=True)).to_have_count(1)
                            expect(page.get_by_text('First item', exact=True)).to_have_count(1)
                            expect(page.get_by_text('Ready', exact=True)).to_have_count(1)
                            expect(page.get_by_role('link', name='Link', exact=True)).to_have_count(1)
                            expect(page.get_by_text('MARKDOWN_FIXTURE', exact=True)).to_have_count(1)
                            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Markdown overflows viewport'
                            page.screenshot(path=str(artifacts / 'markdown.png'), full_page=True)
                            reopen_chat()
                            expect(page.get_by_text('Ready', exact=True)).to_have_count(1)
                            expect(page.get_by_text('Bold result', exact=True)).to_have_count(1)
                            # Force a reply to finish after history was read but before SSE opens.
                            page.get_by_label('消息', exact=True).fill('GAP_FIXTURE')
                            page.get_by_role('button', name='发送消息', exact=True).click()
                            expect(page.get_by_text('Working...', exact=False).last).to_be_visible()
                            def delay_subscription(route):
                                from urllib.parse import urlsplit
                                url = urlsplit(route.request.url)
                                for _ in range(80):
                                    saved = client.get(url.path.replace('/stream', '/messages') + '?' + url.query)
                                    saved.raise_for_status()
                                    if not saved.json()['is_running']:
                                        break
                                    time.sleep(0.2)
                                else:
                                    raise AssertionError('Gap fixture did not finish')
                                route.continue_()
                            page.route('**/sessions/*/stream?*', delay_subscription)
                            reopen_chat()
                            expect(page.get_by_role('button', name='发送消息', exact=True)).to_be_visible(timeout=20000)
                            expect(page.get_by_text('Working... ' + 'more ' * 30, exact=True)).to_be_visible(timeout=20000)
                            page.unroute('**/sessions/*/stream?*', delay_subscription)
                            page.get_by_label('消息', exact=True).fill('STOP_FIXTURE')
                            page.get_by_role('button', name='发送消息', exact=True).click()
                            expect(page.get_by_text('Working...', exact=False).last).to_be_visible()
                            page.get_by_role('button', name='停止生成', exact=True).click()
                            expect(page.get_by_role('button', name='发送消息', exact=True)).to_be_visible()
                            for kind, button in [('ONCE', '允许一次'), ('DENY', '拒绝'), ('RULE', '允许并记住规则')]:
                                page.get_by_label('消息', exact=True).fill(f'CONFIRM_{kind}')
                                page.get_by_role('button', name='发送消息', exact=True).click()
                                expect(page.get_by_role('button', name=button, exact=True)).to_be_visible()
                                if kind == 'ONCE':
                                    reopen_chat()
                                    expect(page.get_by_role('button', name=button, exact=True)).to_be_visible()
                                    expect(page.get_by_role('button', name=button, exact=True)).to_be_enabled()
                                    page.screenshot(path=str(artifacts / 'confirmation.png'), full_page=True)
                                    def fail_confirmation(route):
                                        route.fulfill(status=503, content_type='application/json', body='{"detail":"Fixture confirmation unavailable"}')
                                    page.route('**/chat/', fail_confirmation)
                                    page.get_by_role('button', name=button, exact=True).click()
                                    expect(page.get_by_text('Fixture confirmation unavailable', exact=False)).to_be_visible()
                                    expect(page.get_by_role('button', name=button, exact=True)).to_be_enabled()
                                    assert not (Path(temp) / 'once.txt').exists()
                                    page.unroute('**/chat/', fail_confirmation)
                                page.get_by_role('button', name=button, exact=True).evaluate('(button) => { button.click(); button.click(); }')
                                expect(page.get_by_text(f'Confirmation {kind} completed.', exact=True)).to_be_visible()
                                expect(page.get_by_role('button', name='发送消息', exact=True)).to_be_visible()
                                expect(page.get_by_role('button', name='允许一次', exact=True)).to_have_count(0)
                                assert (Path(temp) / f'{kind.lower()}.txt').exists() == (kind != 'DENY')
                                if kind == 'RULE':
                                    from urllib.parse import urlsplit
                                    session_id = urlsplit(page.url).path.rsplit('/', 1)[-1]
                                    for _ in range(30):
                                        detail = client.get('/sessions/', params={'agent_id': agent['agent_id']})
                                        detail.raise_for_status()
                                        record = next(item['session'] for item in detail.json()['sessions'] if item['session']['id'] == session_id)
                                        rules = record['state']['permission_context']['allow_rules'].get('Write', [])
                                        if rules:
                                            break
                                        time.sleep(0.1)
                                    assert any(rule['behavior'] == 'allow' for rule in rules), 'Allow rule was not persisted'
                            assert len(confirmation_requests) == 4, 'Duplicate confirmation submitted'
                            page.get_by_role('button', name='返回会话列表').click()
                            page.get_by_role('button', name='账户与工作空间').click()
                            page.get_by_role('button', name='退出登录', exact=True).click()
                            expect(page.get_by_role('button', name='登录', exact=True)).to_be_visible()
                            expect(page.get_by_role('checkbox', name='记住密码')).to_be_checked()
                            expect(page.get_by_label('密码', exact=True)).to_have_value('local-fixture-password')
                            expect(page.get_by_label('密码', exact=True)).to_have_attribute('type', 'password')
                            page.reload()
                            expect(page.get_by_label('密码', exact=True)).to_have_value('local-fixture-password')
                            encrypted = page.evaluate('''async () => {
                                const db = await new Promise((resolve,reject) => {const r=indexedDB.open('harbor-mobile-credentials');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
                                const record = await new Promise((resolve,reject) => {const r=db.transaction('vault').objectStore('vault').get('login');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
                                db.close();return record && !record.key.extractable && record.data instanceof ArrayBuffer && !('password' in record);
                            }''')
                            assert encrypted, 'Expected encrypted credential record'
                            page.get_by_role('checkbox', name='记住密码').click()
                            expect(page.get_by_role('checkbox', name='记住密码')).not_to_be_checked()
                            page.reload()
                            expect(page.get_by_label('密码', exact=True)).to_be_editable()
                            expect(page.get_by_label('密码', exact=True)).to_have_value('')
                            expect(page.get_by_label('邮箱', exact=True)).to_have_value('')
                            assert not errors, errors
                            print(json.dumps({'login': True, 'default_chat_home': True, 'remember_password_restore_clear': True, 'encrypted_web_storage': True, 'password_visibility': True, 'invalid_login': True, 'create_chat': True, 'new_chat_inherits_model': True, 'model_name_hidden': True, 'sse': True, 'markdown_stream_history': True, 'confirm_allow_deny_rule_history': True, 'confirm_failure_retry': True, 'history_reconnect': True, 'completion_subscription_gap': True, 'interrupt': True, 'logout': True, 'credential_metadata_only': True, 'browser_errors': errors, 'native_device': 'not tested'}))
                        except Exception:
                            page.screenshot(path=str(artifacts / 'failure.png'), full_page=True)
                            (artifacts / 'failure-dom.html').write_text(page.content(), encoding='utf-8')
                            (artifacts / 'failure.txt').write_text(page.locator('body').inner_text(), encoding='utf-8')
                            raise
                        finally:
                            browser.close()
            finally:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
                for service in (fixture, web):
                    service.shutdown()
                    service.server_close()


if __name__ == '__main__':
    main()
