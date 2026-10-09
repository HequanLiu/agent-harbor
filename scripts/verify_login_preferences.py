"""Read-only UI acceptance plus isolated test credentials; takes a WebView CDP port."""
import json, sys, threading, time, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

EMAIL = 'remember-fixture@example.test'
PASSWORD = 'local-fixture-password'
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def reply(self, status, body):
        content = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers(); self.wfile.write(content)
    def do_GET(self):
        if self.path.endswith('/auth/status'): self.reply(200, {'registration_enabled': True})
        else: self.reply(401, {'detail': 'fixture signed out'})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
        if body.get('password') != PASSWORD:
            self.reply(401, {'detail': 'fixture invalid password'})
        else:
            self.reply(200, {'user': {'id': 'fixture', 'name': 'fixture', 'email': EMAIL}, 'active_tenant_id': 'fixture', 'tenants': []})

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
scope = 'http://127.0.0.1:' + str(server.server_port) + '/test-' + uuid.uuid4().hex + '/'
endpoint = 'http://127.0.0.1:' + sys.argv[1]
for _ in range(60):
    try:
        urllib.request.urlopen(endpoint + '/json/version', timeout=1)
        break
    except Exception:
        time.sleep(.5)
else:
    raise RuntimeError('Desktop debug endpoint did not start')
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(endpoint)
    page = browser.contexts[0].pages[0]
    # Keep all test account traffic and saved credentials separate from the user's server.
    script = """(() => {
      const originalFetch = window.fetch.bind(window);
      window.__loginTestIntercepted = 0;
      window.fetch = (input, init) => {
        const url = new URL(String(input));
        if (url.hostname === 'ipc.localhost') {
          const command = decodeURIComponent(url.pathname.slice(1));
          if (command === 'plugin:http|fetch' || ['load_saved_login','save_login','clear_saved_login'].includes(command)) {
            const args = JSON.parse(init.body);
            if (command === 'plugin:http|fetch') {
              args.clientConfig.url = args.clientConfig.url.replace(/^https?:\/\/[^/]+/, FIXTURE);
            } else args.server = SCOPE;
            window.__loginTestIntercepted++;
            init = {...init, body: JSON.stringify(args)};
          }
        }
        return originalFetch(input, init);
      };
    })();""".replace('FIXTURE', json.dumps('http://127.0.0.1:' + str(server.server_port))).replace('SCOPE', json.dumps(scope))
    page.add_init_script(script)
    try:
        page.reload()
        expect(page.get_by_role('button', name='显示密码', exact=True)).to_be_visible(timeout=5000)
        expect(page.get_by_role('checkbox', name='记住密码', exact=True)).to_be_visible()
        email = page.get_by_label('邮箱', exact=True)
        password = page.get_by_label('密码', exact=True)
        remember = page.get_by_role('checkbox', name='记住密码', exact=True)
        expect(email).to_be_enabled()
        assert page.evaluate('window.__loginTestIntercepted > 0'), 'IPC isolation failed'
        expect(remember).not_to_be_checked()
        email.fill(EMAIL); password.fill('wrong-fixture-password')
        page.get_by_role('button', name='显示密码', exact=True).click()
        expect(password).to_have_attribute('type', 'text')
        page.get_by_role('button', name='隐藏密码', exact=True).click()
        expect(password).to_have_attribute('type', 'password')
        remember.check()
        page.get_by_role('button', name='登录', exact=True).click()
        expect(page.get_by_role('alert')).to_contain_text('fixture invalid password')
        assert page.evaluate("window.__TAURI_INTERNALS__.invoke('load_saved_login', {server: 'ignored'})") is None
        password.fill(PASSWORD)
        page.get_by_role('button', name='登录', exact=True).click()
        expect(remember).to_be_checked()
        page.wait_for_function("window.__TAURI_INTERNALS__.invoke('load_saved_login', {server:'ignored'}).then(v => v !== null)")
        page.reload()
        expect(email).to_have_value(EMAIL)
        expect(password).to_have_value(PASSWORD)
        expect(password).to_have_attribute('type', 'password')
        expect(remember).to_be_checked()
        assert page.evaluate("!Object.values(localStorage).some(v => v.includes('local-fixture-password'))")
        remember.click()
        expect(remember).not_to_be_checked()
        assert page.evaluate("window.__TAURI_INTERNALS__.invoke('load_saved_login', {server:'ignored'})") is None
        page.reload()
        expect(email).to_have_value('')
        expect(password).to_have_value('')
        expect(remember).not_to_be_checked()
        page.get_by_role('button', name='第一次使用？创建账号').click()
        expect(remember).to_have_count(0)
        expect(page.get_by_role('button', name='显示密码', exact=True)).to_be_visible()
        page.get_by_role('button', name='已有账号？返回登录').click()
        expect(password).to_have_attribute('type', 'password')
        Path('.runtime').mkdir(exist_ok=True)
        page.screenshot(path='.runtime/login-preferences-verification.png')
        print(json.dumps({'runtime':'Tauri WebView2','password_visibility':True,'failed_login_not_saved':True,'remember_after_reload':True,'clear_on_uncheck':True,'no_plaintext_local_storage':True,'registration_toggle':True}))
    finally:
        page.evaluate("window.__TAURI_INTERNALS__.invoke('clear_saved_login', {server:'ignored'})")
        browser.close()
        server.shutdown()
