"""Exercise the generated mobile SDK shell in Chromium with a mock native bridge.

This validates the bundled HTML, not a physical iOS/Android WebView.
"""
import json
import socket
import threading
import time

import uvicorn
from fastapi import FastAPI
from playwright.sync_api import sync_playwright, expect

from harbor.connectors.ui_sandbox import render_sandbox
from smoke_mcp_apps import ROOT, crm_html


def main():
    source = (ROOT / 'apps/mobile/src/connector-ui/host-html.ts').read_text(encoding='utf-8')
    shell = json.loads(source.split('export const hostHtml = ', 1)[1].strip().removesuffix(';'))
    crm = crm_html()
    app = FastAPI()
    app.get('/sandbox')(lambda: render_sandbox({}))
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert time.monotonic() < deadline
            time.sleep(.05)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            try:
                page = browser.new_page(viewport={'width': 390, 'height': 844})
                errors, calls = [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                nonce = 'fixture-native-instance-private-nonce'
                session = {'id': 'native-session', 'resource_uri': 'ui://crm/opportunity/v1', 'tool_name': 'crm_create', 'tool_input': {},
                    'tool_result': {'content': [], 'structuredContent': {'title': '移动商机'}}, 'tools': [],
                    'sandbox_url': f'http://127.0.0.1:{sock.getsockname()[1]}/sandbox'}
                def native_post(raw):
                    message = json.loads(raw)
                    assert message['nonce'] == nonce and message['sessionId'] == session['id']
                    kind, payload = message['kind'], message['payload']
                    assert kind == 'rpc', message
                    if payload['method'] == 'resources/read':
                        result = {'contents': [{'uri': session['resource_uri'], 'mimeType': 'text/html;profile=mcp-app', 'text': crm}]}
                    else:
                        calls.append(payload['params'])
                        result = {'content': [], 'structuredContent': payload['params']['arguments']}
                    return {'nonce': nonce, 'id': message['id'], 'result': result}
                page.expose_function('nativePost', native_post)
                page.evaluate("window.ReactNativeWebView={postMessage:raw=>window.nativePost(raw).then(reply=>window.harborReply(reply))}")
                page.set_content(shell)
                page.evaluate('boot=>window.harborBoot(boot)', {'session': session, 'nonce': nonce})
                inner = page.frame_locator('iframe').frame_locator('iframe')
                expect(inner.get_by_label('商机名称')).to_have_value('移动商机', timeout=15000)
                inner.get_by_label('商机名称').fill('原生桥验证')
                inner.get_by_role('button', name='保存商机').click()
                expect(inner.locator('output')).to_have_text('已保存：原生桥验证')
                assert len(calls) == 1
                assert calls[0]['name'] == 'crm_opportunity_save'
                assert calls[0]['arguments'] == {'title': '原生桥验证'}
                assert not errors, errors
                assert page.evaluate('typeof window.harborBoot') == 'undefined'
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
    print('PASS: generated native SDK shell, nonce-tagged bridge, CRM load/edit/save')


if __name__ == '__main__':
    main()
