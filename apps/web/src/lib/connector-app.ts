export interface ConnectorBinding { binding_token: string; resource_uri: string; tool_name: string }
export function connectorBinding(result: unknown): ConnectorBinding | null {
 const value = (result as {metadata?:{connector_ui?:ConnectorBinding}})?.metadata?.connector_ui;
 return value && typeof value.binding_token === 'string' && value.binding_token.length > 0 && typeof value.resource_uri === 'string' && value.resource_uri.startsWith('ui://') && typeof value.tool_name === 'string' ? value : null;
}
export function allowedRpc(method: unknown): boolean { return method === 'tools/call' || method === 'resources/read'; }
export function readAppResource(result: unknown, uri: string): {html:string;csp?:Record<string, string[]>} {
 const contents = (result as {contents?: {uri:string;mimeType:string;text?:string;blob?:string;_meta?:{ui?:{csp?:Record<string,string[]>}}}[]})?.contents;
 if (!contents || contents.length !== 1) throw new Error('连接器界面资源格式不正确');
 const item = contents[0];
 if (item.uri !== uri || item.mimeType !== 'text/html;profile=mcp-app') throw new Error('连接器界面资源不可用');
 let html=item.text;
 if(html===undefined&&typeof item.blob==='string'){
  if(item.blob.length>2_700_000)throw new Error('连接器资源过大');
  try{html=new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(atob(item.blob),c=>c.charCodeAt(0)));}catch{throw new Error('连接器界面编码无效');}
 }
 if(typeof html!=='string'||new TextEncoder().encode(html).length>2_000_000)throw new Error('连接器界面资源不可用');
 return {html,csp:item._meta?.ui?.csp};
}
