import type { CallToolResult, ReadResourceResult, Tool } from '@modelcontextprotocol/client';
import { AppBridge, PostMessageTransport } from '@modelcontextprotocol/ext-apps/app-bridge';
import { z } from 'zod';

import { readAppResource } from '../../lib/connector-app';
export interface AppSession { id:string; resource_uri:string; tool_name:string; tool_input:Record<string,unknown>; tool_result:CallToolResult; tools:Tool[]; sandbox_url:string }
export interface HostCallbacks {
 loading?:(stage:'resource'|'initializing'|'ready')=>void;
 platform?:'web'|'desktop'|'mobile';
 signal?:AbortSignal;
 rpc:(method:string,params:unknown)=>Promise<unknown>;
 message:(params:unknown)=>Promise<void>;
 error:(message:string)=>void;
 close:()=>void;
}
/** Shared by browser, Tauri and the trusted native WebView shell. */
export async function mountConnectorHost(frame:HTMLIFrameElement, session:AppSession, callbacks:HostCallbacks) {
 const sandbox = new URL(session.sandbox_url);
 if (!['http:','https:'].includes(sandbox.protocol) || sandbox.origin === window.location.origin) throw new Error('连接器隔离域未配置：请设置独立的 sandbox origin');
 frame.sandbox.value = 'allow-scripts allow-same-origin allow-forms';
 frame.referrerPolicy = 'no-referrer';
 callbacks.loading?.('resource');
 const resource = readAppResource(await callbacks.rpc('resources/read',{uri:session.resource_uri}),session.resource_uri);
 if(callbacks.signal?.aborted)throw new Error('界面已关闭');
 const bridge = new AppBridge(null,{name:'Agent Harbor',version:'1.0.0'},{serverTools:{},serverResources:{},message:{text:{}}},{hostContext:{theme:document.documentElement.classList.contains('dark')?'dark':'light',platform:callbacks.platform??'web',displayMode:'fullscreen',availableDisplayModes:['fullscreen'],locale:navigator.language,containerDimensions:{width:frame.clientWidth,maxHeight:10000}}});
 bridge.oncalltool = async params => await callbacks.rpc('tools/call',params) as CallToolResult;
 bridge.onreadresource = async params => await callbacks.rpc('resources/read',params) as ReadResourceResult;
 bridge.setRequestHandler('tools/list',{params:z.object({cursor:z.string().optional()}).optional()},async()=>({tools:session.tools}));
 bridge.onmessage = async params => {await callbacks.message(params);return {};};
 bridge.onrequestdisplaymode = async () => ({mode:'fullscreen'});
 bridge.onrequestteardown = callbacks.close;
 bridge.onerror = error => {if(!callbacks.signal?.aborted)callbacks.error(error.message);};
 let initialized = false;
 bridge.oninitialized = () => {
  if(callbacks.signal?.aborted)return;
  initialized = true;
  void (async()=>{
   try {
    await bridge.sendToolInput({arguments:session.tool_input});
    await bridge.sendToolResult(session.tool_result);
    if(!callbacks.signal?.aborted)callbacks.loading?.('ready');
   } catch(error) {if(!callbacks.signal?.aborted)callbacks.error(error instanceof Error?error.message:'表单数据加载失败');}
  })();
 };
 const resize = new ResizeObserver(()=>{ if(initialized) void bridge.sendHostContextChange({containerDimensions:{width:frame.clientWidth,maxHeight:10000}}); });
 const theme = new MutationObserver(()=>{ if(initialized) void bridge.sendHostContextChange({theme:document.documentElement.classList.contains('dark')?'dark':'light'}); });
 let timer:ReturnType<typeof setTimeout>;
 let listener:(event:MessageEvent)=>void;
 let rejectReady:(error:Error)=>void=()=>{};
 const abort=()=>{rejectReady(new Error('界面已关闭'));window.removeEventListener('message',listener);clearTimeout(timer);resize.disconnect();theme.disconnect();void bridge.close();frame.removeAttribute('src');};
 const ready = new Promise<void>((resolve,reject)=>{
  rejectReady=reject;
  timer=setTimeout(()=>reject(new Error('连接器界面加载超时，请重新打开')),15000);
  listener=(event)=>{
   if(event.source===frame.contentWindow && event.origin===sandbox.origin && event.data?.method==='ui/notifications/sandbox-proxy-ready') {clearTimeout(timer);window.removeEventListener('message',listener);resolve();}
  };
  window.addEventListener('message',listener);
 });
 callbacks.signal?.addEventListener('abort',abort,{once:true});
 callbacks.loading?.('initializing');
 frame.src=sandbox.href;
 try {
  await ready;
  if(callbacks.signal?.aborted || !frame.contentWindow)throw new Error('界面已关闭');
  await bridge.connect(new PostMessageTransport(frame.contentWindow!,frame.contentWindow!));
  await bridge.sendSandboxResourceReady(resource);
  resize.observe(frame);theme.observe(document.documentElement,{attributes:true,attributeFilter:['class']});
  timer=setTimeout(()=>{if(!initialized&&!callbacks.signal?.aborted)callbacks.error('连接器界面初始化超时，请关闭后重试');},15000);
 } catch(error) {callbacks.signal?.removeEventListener('abort',abort);window.removeEventListener('message',listener!);clearTimeout(timer!);await bridge.close();throw error;}
 return async()=>{callbacks.signal?.removeEventListener('abort',abort);clearTimeout(timer);resize.disconnect();theme.disconnect();try {if(initialized)await bridge.teardownResource({},{timeout:2000});}catch{/* A disconnected app cannot acknowledge teardown. */}await bridge.close();frame.removeAttribute('src');};
}
