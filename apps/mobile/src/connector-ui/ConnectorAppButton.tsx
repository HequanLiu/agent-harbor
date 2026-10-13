import { useEffect, useRef, useState } from 'react';
import { Alert, Modal, Pressable, Text, View, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { WebView } from 'react-native-webview';
import * as Crypto from 'expo-crypto';
import { useAuth } from '../auth/AuthProvider';
import { parseNativeRequest, messageText, type Binding } from './protocol';
import { hostHtml } from './host-html';

interface Session { id: string; sandbox_url: string; [key: string]: unknown }
interface Approval { id: string; title: string; summary: unknown }
export interface AppButtonProps { binding: Binding; agentId: string; sessionId: string; send: (text: string) => Promise<boolean>; busy: boolean }
const confirm = (title: string, summary: string) => new Promise<boolean>(resolve => Alert.alert(title, summary,
  [{ text: '取消', style: 'cancel', onPress: () => resolve(false) }, { text: '确认', onPress: () => resolve(true) }], { cancelable: true, onDismiss: () => resolve(false) }));

export function ConnectorAppButton({ binding, agentId, sessionId, send, busy }: AppButtonProps) {
  const { api, identity } = useAuth();
  const [open, setOpen] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState('');
  const web = useRef<WebView>(null);
  const live = useRef({ busy, send, agentId, sessionId });
  useEffect(() => { live.current = { busy, send, agentId, sessionId }; }, [busy, send, agentId, sessionId]);
  const instance = useRef<{ nonce: string; session: Session; token: string; tenant: string; requests: Set<string>; approval: boolean; closed: boolean } | null>(null);
  useEffect(() => {
    if (!open) return;
    let stopped = false;
    let created: Session | null = null;
    const token = api.token, tenant = api.tenant;
    queueMicrotask(() => { if (!stopped) { setError(''); setSession(null); } });
    void api.request<Session>('harbor/connector-ui/sessions', { method: 'POST', body: { binding_token: binding.binding_token, agent_id: agentId, session_id: sessionId } }).then(value => {
      created = value;
      if (stopped || api.token !== token || api.tenant !== tenant) { void api.request(`harbor/connector-ui/sessions/${value.id}`, { method: 'DELETE' }).catch(() => {}); return; }
      instance.current = { nonce: Crypto.randomUUID() + Crypto.randomUUID(), session: value, token, tenant, requests: new Set(), approval: false, closed: false };
      setSession(value);
    }).catch(e => { if (!stopped) setError(e instanceof Error ? e.message : '界面无法打开'); });
    return () => { stopped = true; if (instance.current) instance.current.closed = true; instance.current = null; if (created) void api.request(`harbor/connector-ui/sessions/${created.id}`, { method: 'DELETE' }).catch(() => {}); };
  }, [open, binding.binding_token, agentId, sessionId, api, identity?.active_tenant_id]);
  async function close() { if (instance.current?.approval) return; if (await confirm('关闭界面', '请先在连接器中保存更改。确定关闭？')) setOpen(false); }
  async function receive(raw: string) {
    const current = instance.current;
    if (!current || current.closed || api.token !== current.token || api.tenant !== current.tenant) return;
    const request = parseNativeRequest(raw, current.nonce, current.session.id);
    if (!request || current.requests.has(request.id) || current.requests.size >= 100) return;
    current.requests.add(request.id);
    const stillCurrent = () => instance.current === current && !current.closed && api.token === current.token && api.tenant === current.tenant;
    const reply = (result?: unknown, error?: string) => { if (stillCurrent()) web.current?.injectJavaScript(`window.harborReply&&window.harborReply(${JSON.stringify({ nonce: current.nonce, id: request.id, result, error })});true;`); };
    async function ask(title: string, summary: string) {
      if (current!.approval) throw new Error('请先处理当前确认');
      current!.approval = true;
      try { return await confirm(title, summary); } finally { current!.approval = false; }
    }
    try {
      if (request.kind === 'rpc') {
        const response = await api.request<{ result: unknown; error?: { message: string }; approval_required?: Approval }>(`harbor/connector-ui/sessions/${current.session.id}/rpc`, { method: 'POST', body: { jsonrpc: '2.0', id: request.id, method: request.payload.method, params: request.payload.params } });
        if (response.error) throw new Error(response.error.message);
        if (response.approval_required) {
          if (!stillCurrent()) return;
          const a = response.approval_required;
          const approved = await ask(a.title, typeof a.summary === 'string' ? a.summary : JSON.stringify(a.summary, null, 2));
          if (!stillCurrent()) return;
          const decision = await api.request<{ result?: unknown }>(`harbor/connector-ui/approvals/${a.id}/decision`, { method: 'POST', body: { approved } });
          reply(decision.result ?? { content: [{ type: 'text', text: '用户取消操作' }], isError: true });
        } else reply(response.result);
      } else if (request.kind === 'message') {
        const text = messageText(request.payload);
        if (!await ask('发送到当前对话', text)) throw new Error('用户取消发送');
        if (!stillCurrent() || live.current.agentId !== agentId || live.current.sessionId !== sessionId || live.current.busy) throw new Error('当前会话忙碌，请稍后重试');
        if (!await live.current.send(text)) throw new Error('发送未完成，请核对会话后重试');
        reply({});
      } else if (request.kind === 'close') { reply({}); void close(); }
      else { if (stillCurrent()) setError(String(request.payload.message || '连接器界面错误')); reply({}); }
    } catch (e) { reply(undefined, e instanceof Error ? e.message : '请求失败'); }
    finally { current.requests.delete(request.id); }
  }
  return <><Pressable accessibilityRole="button" onPress={() => setOpen(true)} style={{ padding: 12, borderWidth: 1, borderColor: '#ddd', borderRadius: 10, marginTop: 8 }}><Text>打开连接器界面</Text></Pressable>
    <Modal visible={open} animationType="slide" onRequestClose={() => { void close(); }}><SafeAreaView style={{ flex: 1, backgroundColor: '#fff' }}>
      <View style={{ padding: 12, flexDirection: 'row', justifyContent: 'space-between' }}><Text>连接器界面</Text><Pressable accessibilityRole="button" onPress={() => { void close(); }}><Text>关闭</Text></Pressable></View>
      {!!error && <Text accessibilityRole="alert" style={{ padding: 12, color: '#b42318' }}>{error}</Text>}
      {session ? <WebView key={session.id} ref={web} source={{ html: hostHtml }} originWhitelist={['*']} javaScriptEnabled sharedCookiesEnabled={false} thirdPartyCookiesEnabled={false} allowFileAccess={false} allowFileAccessFromFileURLs={false} allowUniversalAccessFromFileURLs={false} javaScriptCanOpenWindowsAutomatically={false} geolocationEnabled={false} mixedContentMode="never" onOpenWindow={() => {}} onShouldStartLoadWithRequest={request => request.isTopFrame === false || request.url === 'about:blank'}
        onLoadEnd={() => { const current = instance.current; if (current && !current.closed) web.current?.injectJavaScript(`window.harborBoot&&window.harborBoot(${JSON.stringify({ session: current.session, nonce: current.nonce })});true;`); }}
        onMessage={event => { void receive(event.nativeEvent.data); }} onError={event => setError(event.nativeEvent.description)} style={{ flex: 1 }} /> : !error ? <ActivityIndicator /> : null}
    </SafeAreaView></Modal></>;
}
