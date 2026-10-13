import { mountConnectorHost, type AppSession } from './host';
type Boot = { session: AppSession; nonce: string };
const native = (window as unknown as { ReactNativeWebView: { postMessage: (s: string) => void } }).ReactNativeWebView;
let started = false;
Object.defineProperty(window, 'harborBoot', { configurable: true, value: async ({ session, nonce }: Boot) => {
  if (started) return;
  started = true;
  delete (window as unknown as Record<string, unknown>).harborBoot;
  let sequence = 0;
  const pending = new Map<string, { resolve: (v: unknown) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }>();
  const send = (kind: string, payload: unknown) => {
    const id = String(++sequence);
    return new Promise<unknown>((resolve, reject) => {
      const timer = setTimeout(() => { pending.delete(id); reject(new Error('请求超时，请核对状态后重试')); }, 60000);
      pending.set(id, { resolve, reject, timer });
      native.postMessage(JSON.stringify({ nonce, sessionId: session.id, id, kind, payload }));
    });
  };
  Object.defineProperty(window, 'harborReply', { configurable: true, value: (reply: { nonce: string; id: string; result?: unknown; error?: string }) => {
    if (reply.nonce !== nonce) return;
    const item = pending.get(reply.id);
    if (!item) return;
    clearTimeout(item.timer); pending.delete(reply.id);
    reply.error ? item.reject(new Error(reply.error)) : item.resolve(reply.result);
  } });
  const frame = document.querySelector('iframe')!;
  try {
    const dispose = await mountConnectorHost(frame, session, { platform: 'mobile', rpc: (method, params) => send('rpc', { method, params }), message: async params => { await send('message', params); }, error: message => { void send('error', { message }).catch(() => {}); }, close: () => { void send('close', {}).catch(() => {}); } });
    window.addEventListener('pagehide', () => { void dispose(); for (const p of pending.values()) { clearTimeout(p.timer); p.reject(new Error('界面已关闭')); } pending.clear(); }, { once: true });
  } catch (error) { void send('error', { message: error instanceof Error ? error.message : '界面加载失败' }).catch(() => {}); }
} });
