import { useContext, useEffect, useRef, useState } from 'react';

import { ConnectorChatContext } from './context';
import { Loader2 } from 'lucide-react';
import { mountConnectorHost, type AppSession } from './host';
import { harborRequest } from '@/api/harbor';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import type { ConnectorBinding } from '@/lib/connector-app';
import { isDesktop } from '@/lib/desktop';
interface Approval {id:string;title:string;summary:unknown;expires_at?:number}
export function ConnectorApp({binding}:{binding:ConnectorBinding}) {
 const chat=useContext(ConnectorChatContext);
 const [open,setOpen]=useState(false),[error,setError]=useState('');
 const [loading,setLoading]=useState<'connecting'|'resource'|'initializing'|'ready'>('connecting');
 const [elapsed,setElapsed]=useState(0);
 const isLoading=open&&!error&&loading!=='ready';
 useEffect(()=>{
  if(!isLoading)return;
  const started=Date.now();
  const timer=setInterval(()=>setElapsed(Math.floor((Date.now()-started)/1000)),1000);
  return ()=>clearInterval(timer);
 },[isLoading]);
 const [approval,setApproval]=useState<Approval|null>(null);
 const pending=useRef<((approved:boolean)=>void)|null>(null);
 const [frame,setFrame]=useState<HTMLIFrameElement|null>(null);
 const activeChat=useRef(chat);
 useEffect(()=>{activeChat.current=chat;},[chat]);
 const approve=(value:boolean)=>{pending.current?.(value);pending.current=null;setApproval(null);};
 useEffect(()=>{
  if(!open || !chat?.agentId || !chat.sessionId || !frame)return;
  setLoading('connecting');
  let cancelled=false;let session:AppSession|undefined;let dispose:(()=>Promise<void>)|undefined;
  const controller=new AbortController();
  const agentId=chat.agentId,sessionId=chat.sessionId;
  const ensureCurrent=()=>{if(cancelled||activeChat.current?.agentId!==agentId||activeChat.current?.sessionId!==sessionId)throw new Error('界面会话已关闭');};
  const ask=(value:Approval)=>{ensureCurrent();if(pending.current)return Promise.reject(new Error('请先处理当前确认'));return new Promise<boolean>(resolve=>{pending.current=resolve;setApproval(value);});};
  void (async()=>{
   try {
    session=await harborRequest<AppSession>('/connector-ui/sessions','POST',{binding_token:binding.binding_token,agent_id:agentId,session_id:sessionId});
    if(cancelled){await harborRequest(`/connector-ui/sessions/${session.id}`,'DELETE');return;}
    dispose=await mountConnectorHost(frame,session,{
     platform:isDesktop?'desktop':'web',
     signal:controller.signal,
     loading:stage=>{if(!cancelled)setLoading(stage);},
     rpc:async(method,params)=>{
      ensureCurrent();
      const response=await harborRequest<{result:unknown;error?:{message:string};approval_required?:Approval}>(`/connector-ui/sessions/${session!.id}/rpc`,'POST',{jsonrpc:'2.0',id:crypto.randomUUID(),method,params});
      ensureCurrent();
      if(response.error)throw new Error(response.error.message);
      if(response.approval_required){
       const approved=await ask(response.approval_required);
       ensureCurrent();
       const decision=await harborRequest<{result?:unknown;cancelled?:boolean}>(`/connector-ui/approvals/${response.approval_required.id}/decision`,'POST',{approved});
       return decision.result ?? {content:[{type:'text',text:'用户取消操作'}],isError:true};
      }
      return response.result;
     },
     message:async params=>{
      const content=(params as {content?:{type:string;text?:string}[]}).content;
      if(!content?.length || content.some(x=>x.type!=='text'||typeof x.text!=='string'))throw new Error('此宿主仅支持文本辅助请求');
      const text=content.map(x=>x.text).join('\n');
      if(text.length>32000)throw new Error('辅助请求过长');
      const approved=await ask({id:'message',title:'发送到当前对话',summary:text});
      const current=activeChat.current;
      if(!approved)throw new Error('用户取消发送');
      if(!current||current.agentId!==agentId||current.sessionId!==sessionId||current.busy)throw new Error('当前会话忙碌，请稍后重试');
      current.send(text);
     },error:message=>{if(!cancelled)setError(message);},close:()=>{if(!pending.current&&window.confirm('请先在连接器中保存更改。确定关闭界面？'))setOpen(false);},
    });
    if(cancelled)await dispose();
   }catch(e){if(!cancelled)setError(e instanceof Error?e.message:'连接器界面加载失败');}
  })();
  return ()=>{cancelled=true;controller.abort();pending.current?.(false);pending.current=null;setApproval(null);void dispose?.();if(session)void harborRequest(`/connector-ui/sessions/${session.id}`,'DELETE').catch(()=>{});};
 },[open,frame,binding.binding_token,chat?.agentId,chat?.sessionId]);
 return <div className="my-3 rounded-xl border p-4"><p className="mb-2 text-sm">连接器交互界面</p><Button variant="outline" disabled={!chat?.sessionId} onClick={()=>{setError('');setLoading('connecting');setElapsed(0);setOpen(true);}}>打开界面</Button>
  <Dialog open={open} onOpenChange={next=>{if(!next&&window.confirm('请先在连接器中保存更改。确定关闭界面？'))setOpen(false);}}><DialogContent className="flex h-[92dvh] max-w-5xl sm:max-w-5xl flex-col p-4" onInteractOutside={e=>e.preventDefault()}><DialogHeader><DialogTitle>连接器界面</DialogTitle><DialogDescription>请在界面中保存更改后关闭。</DialogDescription></DialogHeader>{error&&<p role="alert" className="text-destructive">{error}。工具文本结果仍保留，重新打开不会重复执行原始工具。</p>}
   <div className="relative min-h-0 flex-1" aria-busy={isLoading}>
    {isLoading&&<div role="status" aria-live="polite" className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-background text-center">
     <Loader2 aria-hidden="true" className="size-7 animate-spin text-primary" />
     <p className="text-sm font-medium">{{connecting:'正在连接服务…',resource:'正在加载表单…',initializing:'正在初始化界面…',ready:''}[loading]}</p>
     <p className="text-xs text-muted-foreground">{elapsed>=10?'加载较慢，仍在等待服务响应，请稍候。':'首次打开可能需要一些时间，请稍候。'}</p>
     <span aria-hidden="true" className="text-xs tabular-nums text-muted-foreground">已等待 {elapsed} 秒</span>
    </div>}
    <iframe ref={setFrame} title="连接器应用" className="h-full w-full border-0" />
   </div>
  </DialogContent></Dialog>
  <Dialog open={!!approval} onOpenChange={next=>{if(!next)approve(false);}}><DialogContent><DialogHeader><DialogTitle>{approval?.title}</DialogTitle><DialogDescription>请核对操作内容后决定是否继续。</DialogDescription></DialogHeader><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-sm">{typeof approval?.summary==='string'?approval.summary:JSON.stringify(approval?.summary,null,2)}</pre><div className="flex justify-end gap-2"><Button variant="outline" onClick={()=>approve(false)}>取消</Button><Button onClick={()=>approve(true)}>确认</Button></div></DialogContent></Dialog>
 </div>;
}
