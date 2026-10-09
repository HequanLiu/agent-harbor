"""Acceptance against packaged Tauri executable, not a normal browser."""
from pathlib import Path
import json, os, socket, subprocess, sys, threading, time
from http.server import ThreadingHTTPServer
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.runtime/desktop-test-output'
OUT.mkdir(parents=True,exist_ok=True)
RUN=ROOT/'.runtime'/f'desktop-validation-{int(time.time())}'
RUN.mkdir(parents=True)
sys.path.insert(0,str(ROOT/'scripts'))
from smoke_chat import Fixture, REPLY
def port():
    with socket.socket() as s: s.bind(('127.0.0.1',0)); return s.getsockname()[1]
# Must match VITE_HARBOR_SERVER_URL embedded in the packaged executable.
api_port = int(os.environ.get('HARBOR_DESKTOP_TEST_PORT', '8017'))
with socket.socket() as check:
    check.bind(('127.0.0.1', api_port))
debug_port=port()
base=f'http://127.0.0.1:{api_port}'
fixture=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
threading.Thread(target=fixture.serve_forever,daemon=True).start()
env={**os.environ,'HARBOR_DATA_DIR':str(RUN/'data'),'HARBOR_API_PORT':str(api_port),'NODE_OPTIONS':'--max-old-space-size=512'}
server_log=(RUN/'server.log').open('w',encoding='utf-8')
server=subprocess.Popen([str(ROOT/'.venv/Scripts/python.exe'),'-X','utf8',str(ROOT/'apps/server/main.py')],cwd=ROOT/'apps/server',env=env,stdout=server_log,stderr=server_log,creationflags=subprocess.CREATE_NO_WINDOW)
native=None
try:
    for _ in range(90):
        try:
            if httpx.get(base+'/harbor/health').status_code==200: break
        except httpx.ConnectError: pass
        if server.poll() is not None: raise RuntimeError('Server failed: '+str(RUN/'server.log'))
        time.sleep(.5)
    else: raise RuntimeError('Server startup timeout')
    env.update({'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS':f'--remote-debugging-port={debug_port}', 'WEBVIEW2_USER_DATA_FOLDER':str(RUN/'webview')})
    native=subprocess.Popen([str(ROOT/'apps/web/src-tauri/target/release/agent-harbor.exe')],cwd=ROOT,env=env)
    for _ in range(90):
        try:
            if httpx.get(f'http://127.0.0.1:{debug_port}/json/version').status_code==200: break
        except httpx.ConnectError: pass
        if native.poll() is not None: raise RuntimeError('Native app exited')
        time.sleep(.5)
    else: raise RuntimeError('WebView debug port timeout')
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(f'http://127.0.0.1:{debug_port}')
        page=browser.contexts[0].pages[0]
        errors=[]
        page.on('pageerror',lambda e: (errors.append(str(e)), print('PAGE ERROR:', str(e), flush=True)))
        page.on('console',lambda m: print('CONSOLE:',m.text[:700],flush=True) if m.type=='error' else None)
        expect(page.get_by_role('heading',name='登录工作空间')).to_be_visible(timeout=60000)
        assert page.evaluate('!!window.__TAURI_INTERNALS__'), 'Not a Tauri WebView'
        assert page.url.startswith('http://tauri.localhost'), page.url
        expect(page.locator('#server-url')).to_have_count(0)
        probe_chunk=next(f for f in (ROOT/'apps/web/dist/assets').glob('*.js') if 'plugin:http|fetch_send' in f.read_text(encoding='utf-8'))
        print('HTTP PROBE',page.evaluate('''async ({chunk,url}) => {try { const {fetch}=await import('/assets/'+chunk); const r=await fetch(url);return {status:r.status,text:await r.text()}; } catch(e) { return String(e); }}''',{'chunk':probe_chunk.name,'url':base+'/harbor/auth/status'}),flush=True)
        expect(page.get_by_role('button',name='第一次使用？创建账号')).to_be_visible(timeout=30000)
        page.screenshot(path=str(OUT/'agent-harbor-desktop-login.png'))
        email=f'desktop-{int(time.time())}@example.test'
        password='desktop-fixture-password'
        page.get_by_role('button',name='第一次使用？创建账号').click()
        page.get_by_label('你的名字').fill('桌面端验收')
        page.get_by_label('邮箱',exact=True).fill(email)
        page.get_by_label('密码',exact=True).fill(password)
        page.get_by_label('工作空间名称',exact=True).fill('桌面测试空间')
        page.get_by_role('button',name='创建账号与空间').click()
        expect(page.get_by_label('切换工作空间')).to_be_visible(timeout=30000)
        chunk=next(f for f in (ROOT/'apps/web/dist/assets').glob('*.js') if 'plugin:http|fetch_send' in f.read_text(encoding='utf-8'))
        def request(path,method='GET',body=None):
            return page.evaluate('''async ({chunk,url,method,body}) => {
                const {fetch} = await import('/assets/'+chunk);
                const r=await fetch(url,{method,headers:{'Content-Type':'application/json','X-Tenant-ID':sessionStorage.getItem('harbor_tenant')||''},body:body===null?undefined:JSON.stringify(body)});
                const text=await r.text(); if(!r.ok) throw new Error(r.status+': '+text);
                return text?JSON.parse(text):null;
            }''',{'chunk':chunk.name,'url':base+path,'method':method,'body':body})
        me=request('/harbor/auth/me'); first=me['active_tenant_id']
        credential=request('/credential/','POST',{'data':{'type':'openai_credential','name':'Native local fixture','api_key':'local-fixture-not-a-secret','base_url':f'http://127.0.0.1:{fixture.server_port}/v1'}})
        agent=request('/agent/','POST',{'name':'桌面流式验收 Agent'}); aid=agent['agent_id']
        session=request('/sessions/','POST',{'agent_id':aid,'name':'Tauri 原生网络验收','chat_model_config':{'type':'openai_credential','credential_id':credential['credential_id'],'model':'fixture','parameters':{}}}); sid=session['session_id']
        page.get_by_role('link',name='空间管理').click()
        page.get_by_label('新空间名称').fill('第二个桌面空间')
        page.get_by_role('button',name='创建空间',exact=True).click()
        expect(page.get_by_role('heading',name='第二个桌面空间',exact=True)).to_be_visible(timeout=30000)
        assert aid not in json.dumps(request('/agent/'))
        page.get_by_label('切换工作空间').select_option(first)
        expect(page.get_by_label('切换工作空间')).to_have_value(first,timeout=30000)
        assert aid in json.dumps(request('/agent/'))
        page.goto(f'http://tauri.localhost/#/chat/{aid}/{sid}')
        editor=page.locator('textarea').first
        expect(editor).to_be_visible(timeout=30000)
        editor.fill('Hello from the native desktop acceptance test'); editor.press('Enter')
        expect(page.get_by_text(REPLY,exact=False).first).to_be_visible(timeout=45000)
        page.screenshot(path=str(OUT/'agent-harbor-desktop-chat.png'))
        uploaded=page.evaluate('''async ({chunk,url}) => {
            const {fetch}=await import('/assets/'+chunk);
            const content='---\\nname: desktop-fixture\\ndescription: Native upload acceptance\\n---\\n# Desktop fixture\\n';
            const f=new File([content],'SKILL.md',{type:'text/markdown'});
            const form=new FormData(); form.append('manifest',JSON.stringify({entries:[{path:'desktop-fixture/SKILL.md',size:f.size}]}));form.append('files',f);
            const response=await fetch(url,{method:'POST',body:form,headers:{'X-Tenant-ID':sessionStorage.getItem('harbor_tenant')}});
            return {status:response.status,text:await response.text()};
        }''',{'chunk':chunk.name,'url':base+f'/workspace/skill/upload?agent_id={aid}&session_id={sid}'})
        assert 200<=uploaded['status']<300,uploaded
        assert 'desktop-fixture' in json.dumps(request(f'/workspace/skill?agent_id={aid}&session_id={sid}'))
        # Verify scope blocks insecure remote URLs without contacting a remote host.
        denied=page.evaluate('''async chunk => {try {const {fetch}=await import('/assets/'+chunk);await fetch('http://example.com/');return false;}catch(e){return String(e).includes('not allowed');}}''',chunk.name)
        assert denied, 'HTTP capability did not deny remote plaintext'
        page.get_by_label('退出登录').click()
        expect(page.get_by_role('heading',name='登录工作空间')).to_be_visible(timeout=30000)
        page.get_by_label('邮箱',exact=True).fill(email);page.get_by_label('密码',exact=True).fill(password)
        page.get_by_role('button',name='登录',exact=True).click()
        expect(page.get_by_label('切换工作空间')).to_be_visible(timeout=30000)
        assert not errors,errors
        result={'runtime':'packaged Tauri Windows WebView2','origin':page.url,'registration_login_logout':True,'tenant_switch_isolation':True,'native_cookie_jar':True,'native_chat_sse':True,'native_multipart_skill_upload':True,'insecure_remote_http_denied':True,'provider':'local fixture; no paid model','page_errors':errors}
        (OUT/'agent-harbor-desktop-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))
        browser.close()
except Exception:
    if 'page' in locals():
        try:
            page.screenshot(path=str(OUT/'agent-harbor-desktop-failure.png'))
            print(page.locator('body').inner_text()[-2500:])
        except Exception: pass
    raise
finally:
    if native and native.poll() is None: native.terminate(); native.wait(timeout=15)
    server.terminate(); server.wait(timeout=15);server_log.close();fixture.shutdown()
