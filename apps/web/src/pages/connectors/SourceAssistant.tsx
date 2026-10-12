import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { client } from '@/api/client';
import { Button } from '@/components/ui/button';
import { useHarbor } from '@/context/HarborContext';

interface Installation { agent_id: string; session_id: string }
interface Started extends Installation { status: string; url: string }
const keyOf = (item: Installation) => JSON.stringify([item.agent_id, item.session_id]);

export function SourceAssistant({ connectorId, draftId, assetId, disabled }: { connectorId: string; draftId: string; assetId: string; disabled: boolean }) {
  const identity = useHarbor();
  const navigate = useNavigate();
  const base = `/harbor/connectors/${encodeURIComponent(connectorId)}`;
  const installations = useQuery({ queryKey: ['connector-installations', identity.active_tenant_id, identity.user.id, connectorId], queryFn: () => client.get<{ items: Installation[] }>(`${base}/installations`, undefined, { silent: true }) });
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const items = installations.data?.items ?? [];
  const target = items.length === 1 ? items[0] : items.find(item => keyOf(item) === selected);
  async function start() {
    if (!target || busy || disabled) return;
    setBusy(true); setError('');
    try {
      const result = await client.post<Started>(`${base}/parse-source`, { draft_id: draftId, asset_id: assetId, agent_id: target.agent_id, session_id: target.session_id }, undefined, { silent: true });
      const expected = `/chat/${encodeURIComponent(result.agent_id)}/${encodeURIComponent(result.session_id)}?orderDraftId=${encodeURIComponent(draftId)}`;
      if (result.status !== 'started' || result.url !== expected) throw new Error('服务返回了无效的会话地址，请刷新后查看会话');
      navigate(result.url);
    } catch (e) { setError(e instanceof Error ? e.message : '识别任务未启动，请重试'); }
    finally { setBusy(false); }
  }
  return <div className="mt-3 space-y-2">
    {installations.isPending && <p className="text-xs text-muted-foreground" role="status">正在读取已安装会话…</p>}
    {installations.error && <p role="alert" className="text-xs text-destructive">无法读取安装目标。<button className="ml-2 underline" onClick={() => void installations.refetch()}>重试</button></p>}
    {!installations.isPending && !installations.error && items.length === 0 && <p className="text-xs text-muted-foreground">请先<Link className="mx-1 underline" to="/connectors">将连接器安装到 Agent 会话</Link>，再交给助手识别。</p>}
    {items.length > 1 && <label className="block text-xs">识别会话<select className="mt-1 w-full rounded-md border bg-background p-2" value={selected} disabled={busy || disabled} onChange={event => setSelected(event.target.value)}><option value="">选择已安装的会话</option>{items.map(item => <option key={keyOf(item)} value={keyOf(item)}>{item.agent_id} / {item.session_id}</option>)}</select></label>}
    {items.length === 1 && <p className="break-all text-xs text-muted-foreground">识别会话：{target?.agent_id} / {target?.session_id}</p>}
    <Button size="sm" disabled={busy || disabled || !target} onClick={() => void start()}>{busy ? '正在启动识别…' : '交给助手识别'}</Button>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
  </div>;
}
