export interface Binding { binding_token: string; resource_uri: string; tool_name: string }
export function getBinding(block: unknown): Binding | null {
  const b = (block as { metadata?: { connector_ui?: Binding } })?.metadata?.connector_ui;
  return b && typeof b.binding_token === 'string' && b.binding_token.length > 0 && typeof b.resource_uri === 'string' && b.resource_uri.startsWith('ui://') && typeof b.tool_name === 'string' ? b : null;
}
export interface NativeRequest { nonce: string; sessionId: string; id: string; kind: 'rpc' | 'message' | 'close' | 'error'; payload: Record<string, unknown> }
export function parseNativeRequest(raw: string, nonce: string, sessionId: string): NativeRequest | null {
  if (raw.length > 2_100_000) return null;
  try {
    const value = JSON.parse(raw) as NativeRequest;
    if (!value || value.nonce !== nonce || value.sessionId !== sessionId || typeof value.id !== 'string' || !value.id || value.id.length > 100 || !['rpc', 'message', 'close', 'error'].includes(value.kind) || !value.payload || typeof value.payload !== 'object' || Array.isArray(value.payload)) return null;
    if (value.kind === 'rpc' && !['tools/call', 'resources/read'].includes(String(value.payload.method))) return null;
    return value;
  } catch { return null; }
}
export function messageText(payload: Record<string, unknown>): string {
  const content = payload.content as { type: string; text?: string }[];
  if (!Array.isArray(content) || !content.length || content.some(c => !c || c.type !== 'text' || typeof c.text !== 'string')) throw new Error('此宿主仅支持文本辅助请求');
  const text = content.map(c => c.text).join('\n');
  if (text.length > 32000) throw new Error('辅助请求过长');
  return text;
}
