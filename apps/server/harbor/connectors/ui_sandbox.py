"""Fixed MCP Apps sandbox relay with server-enforced network policy."""
import html
import json
from urllib.parse import urlsplit

from starlette.responses import HTMLResponse


def _origins(csp, key):
    values = csp.get(key, [])
    if not isinstance(values, list) or len(values) > 20:
        raise ValueError('Invalid UI CSP origins')
    result = []
    for value in values:
        if not isinstance(value, str) or len(value) > 300:
            raise ValueError('Invalid UI CSP origin')
        parsed = urlsplit(value)
        try:
            port = parsed.port
        except ValueError:
            raise ValueError('Invalid UI CSP port') from None
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
                or parsed.username or parsed.password or parsed.path not in {'', '/'}
                or parsed.query or parsed.fragment
                or any(c in value for c in " ;*'\"<>\\\r\n\t")):
            raise ValueError('UI CSP entries must be exact HTTP origins')
        host = parsed.hostname
        if ':' in host:
            host = '[' + host + ']'
        result.append(f'{parsed.scheme}://{host}' + (f':{port}' if port else ''))
    return ' '.join(sorted(set(result))) or "'none'"


def render_sandbox(csp=None):
    """Return a fixed relay; UI-supplied CSP/sandbox overrides are ignored."""
    if csp is None:
        csp = {}
    if not isinstance(csp, dict):
        raise ValueError('Invalid UI CSP')
    connects = _origins(csp, 'connectDomains')
    resources = _origins(csp, 'resourceDomains')
    frames = _origins(csp, 'frameDomains')
    resource_sources = '' if resources == "'none'" else ' ' + resources
    frame_sources = '' if frames == "'none'" else ' ' + frames
    # The outer relay permits its srcdoc child; the child's policy removes that
    # permission unless the connector explicitly declared nested frame origins.
    common = ("default-src 'none'; script-src 'unsafe-inline'" + resource_sources
              + "; style-src 'unsafe-inline'" + resource_sources
              + '; img-src data: blob:' + resource_sources
              + '; font-src data:' + resource_sources
              + '; media-src data: blob:' + resource_sources
              + '; connect-src ' + connects
              + "; object-src 'none'; base-uri 'none'; form-action 'none'")
    inner_policy = common + '; frame-src ' + frames
    outer_policy = common + "; frame-src 'self' about: blob: data:" + frame_sources
    meta = '<meta http-equiv="Content-Security-Policy" content="' + html.escape(inner_policy, quote=True) + '">'
    encoded_meta = json.dumps(meta).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    body = _RELAY.replace('__POLICY_META__', encoded_meta)
    return HTMLResponse(body, headers={
        'Content-Security-Policy': outer_policy,
        'Cache-Control': 'no-store',
        'Referrer-Policy': 'no-referrer',
        'X-Content-Type-Options': 'nosniff',
        'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    })


_RELAY = '''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body,iframe{margin:0;padding:0;width:100%;height:100%;border:0;overflow:hidden}</style>
</head><body><script>
(() => {
  const policyMeta = __POLICY_META__;
  const frame = document.createElement('iframe');
  frame.setAttribute('sandbox', 'allow-scripts allow-forms');
  frame.setAttribute('referrerpolicy', 'no-referrer');
  frame.title = 'Connector application';
  document.body.appendChild(frame);
  let loaded = false;
  let parentOrigin = null;
  const reserved = 'ui/notifications/sandbox-';
  window.addEventListener('message', event => {
    const message = event.data;
    if (!message || typeof message !== 'object' || message.jsonrpc !== '2.0') return;
    if (event.source === window.parent) {
      if (parentOrigin !== null && event.origin !== parentOrigin) return;
      if (message.method === 'ui/notifications/sandbox-resource-ready') {
        if (loaded || typeof message.params?.html !== 'string' || message.params.html.length > 8388608) return;
        parentOrigin = event.origin;
        loaded = true;
        // Put enforcing policy before any connector-controlled markup.
        frame.srcdoc = '<!doctype html><head>' + policyMeta + '</head>' + message.params.html;
      } else if (loaded && !String(message.method || '').startsWith(reserved)) {
        frame.contentWindow.postMessage(message, '*');
      }
    } else if (event.source === frame.contentWindow && loaded
               && !String(message.method || '').startsWith(reserved)) {
      window.parent.postMessage(message, parentOrigin === 'null' ? '*' : parentOrigin);
    }
  });
  window.parent.postMessage({jsonrpc:'2.0',method:'ui/notifications/sandbox-proxy-ready',params:{}}, '*');
})();
</script></body></html>'''
