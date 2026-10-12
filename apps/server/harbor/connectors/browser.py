"""Establish the OAuth cookie in the system browser."""
import secrets
from starlette.responses import HTMLResponse


def browser_page():
    nonce=secrets.token_urlsafe(24)
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>连接器授权</title><p id="status">正在前往授权页面…</p>
<script nonce="NONCE">
(async () => {
  const ticket = location.hash.slice(1);
  history.replaceState(null, '', location.pathname);
  try {
    if (!ticket) throw new Error();
    const response = await fetch(location.pathname, {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ticket})
    });
    if (!response.ok) throw new Error();
    const result = await response.json();
    const url = new URL(result.authorization_url);
    if (url.username || url.password ||
        (url.protocol !== 'https:' && !(url.protocol === 'http:' &&
         ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)))) throw new Error();
    location.replace(url.href);
  } catch {
    document.getElementById('status').textContent = '授权入口已过期或无法打开，请返回 AgentHarbor 重新点击授权连接。';
  }
})();
</script></html>'''.replace('NONCE',nonce)
    return HTMLResponse(html,headers={
        'Cache-Control':'no-store','Referrer-Policy':'no-referrer',
        'Content-Security-Policy':f"default-src 'none'; script-src 'nonce-{nonce}'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
    })
