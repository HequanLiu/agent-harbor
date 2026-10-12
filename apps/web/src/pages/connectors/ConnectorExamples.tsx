import { useQueryClient } from '@tanstack/react-query';
import { ArrowUpRight, LoaderCircle, MessageSquareText } from 'lucide-react';
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { sessionApi } from '@/api';
import { connectorApi, type Connector } from '@/api/connectors';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { useAgents } from '@/hooks/useAgents';
import { useAvailableModels } from '@/hooks/useAvailableModels';

function ExamplesContent({ connector, enabled }: { connector: Connector; enabled: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { agents, loading, error: agentsError } = useAgents();
  const { groups, loading: modelsLoading } = useAvailableModels();
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inFlight = useRef(false);
  const agentId = selected || agents.find(agent => agent.id === localStorage.getItem('chat_last_agent'))?.id || agents[0]?.id;
  const examples = connector.source === 'dresscode-mes' ? [
    '帮我查询最近的订单，整理订单状态和交期。',
    '我想录入一笔订单，请引导我提供资料，并生成订单草稿供我确认。',
    '我想修改已有订单，请先询问订单编号和修改内容，再生成修改草稿供我确认。',
  ] : [
    `介绍一下 ${connector.name} 可以帮我完成哪些操作，并给出使用建议。`,
    `查看 ${connector.name} 的可用工具，告诉我执行这些操作需要提供哪些信息。`,
  ];

  async function start(prompt: string) {
    if (!agentId || inFlight.current || !enabled || connector.status !== 'connected') return;
    inFlight.current = true;
    setBusy(true); setError('');
    let createdSession: string | undefined;
    try {
      const { sessions } = await sessionApi.list(agentId);
      const seed = (sessions.find(item => item.session.id === localStorage.getItem('chat_last_session')) ?? sessions[0])?.session.config;
      const candidate = Object.entries(groups).flatMap(([type, items]) => items.flatMap(item => item.models.slice(0, 1).map(model => ({ type, credential_id: item.credential.id, model: model.name, parameters: {} }))))[0];
      const model = seed?.chat_model_config ?? candidate;
      if (!model) throw new Error('请先在对话中配置可用模型，再使用操作示例。');
      const { session_id } = await sessionApi.create({ agent_id: agentId, chat_model_config: model, fallback_chat_model_config: seed?.fallback_chat_model_config });
      createdSession = session_id;
      await connectorApi.select(agentId, session_id, [connector.id]);
      const result = await sessionApi.list(agentId);
      queryClient.setQueryData(['sessions', agentId], result.sessions);
      navigate(`/chat/${encodeURIComponent(agentId)}/${encodeURIComponent(session_id)}`, {
        state: { connectorExample: { agentId, sessionId: session_id, prompt: `使用 ${connector.name} 连接器：${prompt}` } },
      });
    } catch (cause) {
      setError(`${cause instanceof Error ? cause.message : '创建对话失败，请重试'}${createdSession ? '（已创建空对话，可在对话列表中查看。）' : ''}`);
    } finally { inFlight.current = false; setBusy(false); }
  }

  return <>
    <DialogHeader><DialogTitle>{connector.name} · 操作示例</DialogTitle><DialogDescription>点击一个示例，将新建对话、选中此连接器并直接发送。</DialogDescription></DialogHeader>
    <label className="space-y-2 text-sm"><span>使用 Agent</span><select aria-label="使用 Agent" className="w-full rounded-md border bg-background p-2" value={agentId ?? ''} disabled={busy || loading} onChange={event => setSelected(event.target.value)}>{!agents.length && <option value="">{loading ? '正在加载…' : '暂无 Agent'}</option>}{agents.map(agent => <option key={agent.id} value={agent.id}>{agent.data.name}</option>)}</select></label>
    {connector.status !== 'connected' && <p className="text-sm text-muted-foreground">请先授权连接，再使用示例。</p>}
    {!loading && !agents.length && <p className="text-sm text-muted-foreground">请先在对话页创建 Agent。</p>}
    <div className="space-y-2">{examples.map(prompt => <button key={prompt} className="flex w-full items-start gap-3 rounded-lg border p-4 text-left text-sm transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50 disabled:cursor-not-allowed" disabled={busy || loading || modelsLoading || !agentId || !enabled || connector.status !== 'connected'} onClick={() => void start(prompt)}><span className="flex-1">{prompt}</span><ArrowUpRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" /></button>)}</div>
    {busy && <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />正在准备新对话…</p>}
    {(error || agentsError) && <p role="alert" className="text-sm text-destructive">{error || agentsError?.message}</p>}
  </>;
}

export function ConnectorExamples({ connector, enabled }: { connector: Connector; enabled: boolean }) {
  return <Dialog><DialogTrigger asChild><Button size="sm" variant="outline"><MessageSquareText />操作示例</Button></DialogTrigger><DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-lg"><ExamplesContent connector={connector} enabled={enabled} /></DialogContent></Dialog>;
}
