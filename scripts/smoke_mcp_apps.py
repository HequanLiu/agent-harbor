"""Real App/AppBridge browser round trip using CRM and the MES UI artifact.

Run against isolated Vite: python scripts/smoke_mcp_apps.py http://127.0.0.1:5188
HTTP business responses are fixtures; no model calls or real MES writes occur.
"""
import copy
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI
from playwright.sync_api import sync_playwright, expect

from harbor.connectors.ui_sandbox import render_sandbox

ROOT = Path(__file__).resolve().parents[1]
MES = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('D:/WorkProject/mes.project/mes.clothes.mcp')


def crm_html():
    candidates = [ROOT / 'apps/web/node_modules/esbuild/lib/main.js', MES / 'ui/node_modules/esbuild/lib/main.js']
    module = next((path for path in candidates if path.exists()), None)
    assert module, 'Install the UI build dependencies before browser acceptance'
    code = "import {pathToFileURL} from 'node:url'; const {build}=await import(pathToFileURL(process.argv[1])); const r=await build({entryPoints:[process.argv[2]],bundle:true,write:false,format:'iife',minify:true}); process.stdout.write(r.outputFiles[0].text);"
    built = subprocess.run(['node', '--max-old-space-size=256', '--input-type=module', '-e', code, str(module),
                            str(ROOT / 'apps/web/tests/fixtures/crm-app.ts')], capture_output=True, check=True)
    return '<!doctype html><html><body><script>' + built.stdout.decode().replace('</script', '<\\/script') + '</script></body></html>'


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5188'
    crm = crm_html()
    mes_html = (MES / 'src/mes_mcp/assets/order-editor.html').read_text(encoding='utf-8')
    sys.path.insert(0, str(MES / 'src'))
    from mes_mcp.orders.schema import OrderDraftInput
    schema = OrderDraftInput.model_json_schema()
    draft = {'draft_id': 'fixture-draft', 'revision': 1, 'status': 'editing',
             'payload': OrderDraftInput().model_dump(mode='json')}
    app = FastAPI()

    @app.get('/sandbox')
    def sandbox():
        return render_sandbox({})

    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sandbox_url = f'http://127.0.0.1:{sock.getsockname()[1]}/sandbox'
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            assert time.monotonic() < deadline
            time.sleep(.05)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            try:
                for kind, viewport in [('crm', {'width': 1280, 'height': 900}), ('mes', {'width': 1280, 'height': 1000}),
                                       ('mes', {'width': 390, 'height': 844})]:
                    state = copy.deepcopy(draft)
                    calls = []
                    uploaded = bytearray()
                    page = browser.new_page(viewport=viewport)
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    uri = 'ui://mes/order-editor/v1' if kind == 'mes' else 'ui://crm/opportunity/v1'
                    def result(value):
                        return {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}], 'structuredContent': value}
                    def api(route):
                        nonlocal state
                        path = urlsplit(route.request.url).path
                        if route.request.method == 'DELETE':
                            route.fulfill(status=204)
                        elif path.endswith('/decision'):
                            if route.request.post_data_json['approved']:
                                state['status'] = 'committed'
                                state['result'] = {'orderId': 'fixture-order'}
                                route.fulfill(json={'result': result(state)})
                            else:
                                route.fulfill(json={'cancelled': True})
                        elif path.endswith('/sessions'):
                            route.fulfill(json={'id': 'fixture-session', 'resource_uri': uri, 'tool_name': 'open',
                                'tool_input': {}, 'tool_result': result(state if kind == 'mes' else {'title': '初始商机'}),
                                'tools': [], 'sandbox_url': sandbox_url})
                        elif path.endswith('/rpc'):
                            request = route.request.post_data_json
                            if request['method'] == 'resources/read':
                                value = {'contents': [{'uri': uri, 'mimeType': 'text/html;profile=mcp-app', 'text': mes_html if kind == 'mes' else crm}]}
                            else:
                                name = request['params']['name']
                                args = request['params'].get('arguments', {})
                                calls.append((name, args))
                                if name == 'crm_opportunity_save':
                                    value = result({'title': args['title']})
                                elif name == 'mes_order_schema_get':
                                    value = result(schema)
                                elif name == 'mes_order_draft_get':
                                    value = result(state)
                                elif name == 'mes_order_draft_patch':
                                    assert args['expected_revision'] == state['revision']
                                    state['payload'].update({k: v for k, v in args['changes'].items() if k != 'reviewed_fields'})
                                    state['revision'] += 1
                                    value = result(state)
                                elif name == 'mes_order_source_upload_begin':
                                    assert args['filename'] == 'source.txt' and args['size'] == 197000
                                    value = result({'upload_id': 'fixture-upload', 'chunk_bytes': 192 * 1024})
                                elif name == 'mes_order_source_upload_chunk':
                                    import base64
                                    assert args['offset'] == len(uploaded)
                                    uploaded.extend(base64.b64decode(args['data'], validate=True))
                                    value = result({'offset': len(uploaded)})
                                elif name == 'mes_order_source_upload_finish':
                                    assert uploaded == b'x' * 197000
                                    value = result({'asset_id': 'fixture-source', 'filename': 'source.txt', 'media_type': 'text/plain'})
                                elif name == 'mes_order_source_attach':
                                    assert args['expected_revision'] == state['revision']
                                    state['payload']['sources'] = [{'asset_id': 'fixture-source', 'filename': 'source.txt', 'media_type': 'text/plain'}]
                                    state['revision'] += 1
                                    value = result(state)
                                elif name == 'mes_order_draft_validate':
                                    state['status'] = 'ready'
                                    state['preview'] = {'content_hash': 'fixture-hash', 'issues': []}
                                    value = result(state)
                                elif name == 'mes_order_approval_prepare':
                                    route.fulfill(json={'jsonrpc': '2.0', 'id': request['id'], 'approval_required': {
                                        'id': 'fixture-approval', 'title': '确认录入 MES 订单', 'summary': 'MCP-APP-SMOKE 当前版本'}})
                                    return
                                else:
                                    raise AssertionError(f'Unexpected fixture tool: {name}')
                            route.fulfill(json={'jsonrpc': '2.0', 'id': request['id'], 'result': value})
                        else:
                            raise AssertionError(f'Unexpected fixture route: {path}')
                    page.route('**/harbor/connector-ui/**', api)
                    background = '&background=1' if '--background' in sys.argv else ''
                    page.goto(base + '/tests/fixtures/connector-app.html?app=' + kind + background)
                    page.get_by_role('button', name='打开界面').click()
                    if viewport['width'] > 1000:
                        expect(page.locator('iframe[title="连接器应用"]')).to_be_visible()
                        assert page.locator('iframe[title="连接器应用"]').bounding_box()['width'] > 700
                    inner = page.frame_locator('iframe[title="连接器应用"]').frame_locator('iframe')
                    if kind == 'crm':
                        expect(inner.get_by_label('商机名称')).to_have_value('初始商机', timeout=30000)
                        inner.get_by_label('商机名称').fill('跨系统通用表单')
                        inner.get_by_role('button', name='保存商机').click()
                        expect(inner.locator('output')).to_have_text('已保存：跨系统通用表单')
                        assert calls[-1] == ('crm_opportunity_save', {'title': '跨系统通用表单'})
                        inner.get_by_role('button', name='请求助手').click()
                        page.get_by_role('button', name='确认', exact=True).click()
                        expect(page.get_by_test_id('message')).to_have_text('请分析当前商机')
                        expect(inner.locator('output')).to_have_text('已发送')
                    else:
                        expect(inner.get_by_label('款号', exact=True)).to_be_visible(timeout=30000)
                        inner.get_by_label('款号', exact=True).fill('MCP-APP-SMOKE')
                        inner.get_by_role('button', name='保存草稿', exact=True).click()
                        expect(inner.get_by_role('button', name='保存草稿', exact=True)).to_be_disabled()
                        assert state['payload']['order']['style_num'] == 'MCP-APP-SMOKE'
                        inner.locator('input[type="file"]').first.set_input_files({'name': 'source.txt', 'mimeType': 'text/plain', 'buffer': b'x' * 197000})
                        expect(inner.get_by_text('source.txt', exact=True)).to_be_visible()
                        assert len([name for name, _ in calls if name == 'mes_order_source_upload_chunk']) == 2
                        inner.get_by_role('button', name='校验并预览').click()
                        expect(inner.get_by_text('我已核对以上订单、款式、PO 数量和 BOM，确认将当前版本写入 MES。')).to_be_visible()
                        assert any(name == 'mes_order_draft_validate' for name, _ in calls)
                        inner.get_by_label('我已核对以上订单、款式、PO 数量和 BOM，确认将当前版本写入 MES。').check()
                        inner.get_by_role('button', name='确认并录入', exact=True).click()
                        expect(page.get_by_role('heading', name='确认录入 MES 订单')).to_be_visible()
                        page.get_by_role('button', name='取消', exact=True).click()
                        expect(inner.get_by_role('alert')).to_be_visible()
                        assert state['status'] == 'ready'
                        inner.get_by_role('button', name='确认并录入', exact=True).click()
                        page.get_by_role('button', name='确认', exact=True).click()
                        expect(inner.get_by_text('订单已成功录入 MES，订单 ID：fixture-order。')).to_be_visible()
                        assert state['status'] == 'committed'
                    assert not errors, errors
                    print(f"PASS: {kind} at {viewport['width']}px", flush=True)
                    page.close()
            finally:
                if sys.exc_info()[0] is not None and browser.contexts:
                    for context in browser.contexts:
                        for current in context.pages:
                            print('Fixture failure:', current.locator('body').inner_text()[:1500])
                            print('Frames:', [frame.url for frame in current.frames])
                    print('Page errors:', errors)
                    print('Tool calls:', [(name, list(args)) for name, args in calls])
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
    print('PASS: official SDK host + CRM app + MES artifact; edit/save/upload/validate/approval at desktop and phone viewport')


if __name__ == '__main__':
    main()
