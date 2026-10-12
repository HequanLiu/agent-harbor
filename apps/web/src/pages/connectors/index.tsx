import { useQuery, useQueryClient } from '@tanstack/react-query';
import { KeyRound, LoaderCircle, Plug, RefreshCw, Trash2, Unplug, Upload, Wrench } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { ConnectorExamples } from './ConnectorExamples';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { ComponentProps } from 'react';

import { connectorApi } from '@/api/connectors';
import type { Connector, ConnectorTool } from '@/api/connectors';
import { Button } from '@/components/ui/button';
import { useHarbor } from '@/context/HarborContext';
import { authorizeConnector } from '@/lib/connector-validation';
import { isDesktop, openConnectorBrowser } from '@/lib/desktop';

export function ConnectorsPage() {
  const identity = useHarbor();
  const queryClient = useQueryClient();
  const queryKey = ['connectors', identity.active_tenant_id, identity.user.id];
  const connectors = useQuery({ queryKey, queryFn: connectorApi.list, refetchOnWindowFocus: 'always' });
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [tools, setTools] = useState<Record<string, ConnectorTool[]>>({});
  const upload = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const onFocus = () => { void queryClient.invalidateQueries({ queryKey: ['connectors', identity.active_tenant_id, identity.user.id] }); };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [queryClient, identity.active_tenant_id, identity.user.id]);
  const enabled = connectors.data?.enabled === true;
  async function run(key: string, action: () => Promise<void>) {
    if (busy) return;
    setBusy(key); setError(''); setNotice('');
    try { await action(); }
    catch (e) { setError(e instanceof Error ? e.message : '操作失败，请重试'); }
    finally { setBusy(''); }
  }
  async function refresh() {
    await queryClient.invalidateQueries({ queryKey });
  }
  function authorize(item: Connector) {
    void run(`${item.id}:authorize`, async () => {
      await authorizeConnector({
        desktop: isDesktop,
        request: external => connectorApi.authorize(item.id, external),
        openPopup: () => window.open('about:blank', '_blank'),
        openExternal: openConnectorBrowser,
      });
      setNotice(isDesktop
        ? '已打开系统浏览器，请完成授权后返回客户端，连接状态会自动刷新。'
        : '请在新窗口完成授权，返回此页后会自动刷新，也可点击刷新。');
    });
  }

  return <div className="h-full overflow-auto p-6 sm:p-10"><div className="mx-auto max-w-4xl space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="mb-2 text-xs tracking-widest text-teal-600">CONNECTORS</p><h1 className="text-2xl font-semibold">连接器</h1><p className="mt-2 text-sm text-muted-foreground">连接外部服务，在对话中按需使用。</p></div>
      <div className="flex gap-2">
        <Button variant="outline" disabled={Boolean(busy) || connectors.isFetching} onClick={() => void connectors.refetch()}><RefreshCw className={connectors.isFetching ? 'animate-spin' : ''} />刷新</Button>
        <Button disabled={!enabled || Boolean(busy)} onClick={() => upload.current?.click()}><Upload />{busy === 'import' ? '正在导入…' : '导入 ZIP'}</Button>
        <input ref={upload} aria-label="导入 ZIP" className="hidden" type="file" accept=".zip,application/zip" onChange={event => {
          const file = event.target.files?.[0]; event.target.value = '';
          if (file) void run('import', async () => { const item = await connectorApi.importArchive(file); await refresh(); setNotice(`已导入 ${item.name}，请继续授权。`); });
        }} />
      </div>
    </header>
    <p className="text-xs text-muted-foreground">支持最大 5 MiB 的 ZIP 包。授权凭据保存在服务端。</p>
    {(error || connectors.error) && <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{error || connectors.error?.message}</p>}
    {notice && <p role="status" className="rounded-lg bg-muted p-3 text-sm">{notice}</p>}
    {connectors.isPending ? <p role="status">正在读取连接器…</p> : connectors.data && !enabled ? <p className="rounded-lg border p-4 text-sm">当前服务未启用连接器，请联系管理员开启。</p> : null}
    {enabled && connectors.data?.items.length === 0 && <div className="rounded-xl border border-dashed p-10 text-center"><Plug className="mx-auto mb-3 size-8 text-muted-foreground" /><p className="font-medium">尚未导入连接器</p><p className="mt-2 text-sm text-muted-foreground">从外部服务下载 ZIP 包，然后点击“导入 ZIP”。</p></div>}
    {connectors.data?.items.map(item => <section key={item.id} className="space-y-4 rounded-xl border p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><h2 className="break-words font-semibold">{item.name} <span className="text-xs font-normal text-muted-foreground">{item.version}</span></h2><p className="mt-1 break-words text-sm text-muted-foreground">{item.description}</p></div><span className={`rounded-full px-3 py-1 text-xs ${item.status === 'connected' ? 'bg-teal-500/10 text-teal-700 dark:text-teal-300' : 'bg-muted text-muted-foreground'}`}>{item.status === 'connected' ? '已连接' : '待授权'}</span></div>
      <p className="break-all text-xs text-muted-foreground">来源：{item.source}</p>
      <div className="flex flex-wrap gap-2 text-xs">{item.skills.map(skill => <span className="rounded-md bg-muted px-2 py-1" key={skill}>{skill}</span>)}{item.skills.length === 0 && <span className="text-muted-foreground">此包不包含技能</span>}</div>
      <div className="flex flex-wrap items-center gap-2">
        <ConnectorExamples connector={item} enabled={enabled && !busy} />
        <IconAction label={item.status === 'connected' ? '重新授权' : '授权连接'} disabled={!enabled || Boolean(busy)} onClick={() => authorize(item)}>{busy === `${item.id}:authorize` ? <LoaderCircle className="animate-spin" /> : <KeyRound />}</IconAction>
        <IconAction label="发现工具" disabled={!enabled || Boolean(busy) || item.status !== 'connected'} onClick={() => void run(`${item.id}:tools`, async () => { const result = await connectorApi.tools(item.id); setTools(current => ({ ...current, [item.id]: result.tools })); setNotice(`已发现 ${result.tools.length} 个工具。`); })}>{busy === `${item.id}:tools` ? <LoaderCircle className="animate-spin" /> : <Wrench />}</IconAction>
        <IconAction label={item.status === 'connected' ? '断开' : '重试撤销授权'} disabled={!enabled || Boolean(busy)} onClick={() => {
          if (window.confirm(`断开 ${item.name}？已安装的技能文件会保留，外部工具将无法继续调用。`)) void run(`${item.id}:disconnect`, async () => { const result = await connectorApi.disconnect(item.id); setTools(current => { const next = { ...current }; delete next[item.id]; return next; }); await refresh(); setNotice(result.remote_revoked ? '连接已断开，远端授权已撤销。' : '本地连接已停用，远端授权尚未确认撤销，请重试撤销授权。'); });
        }}><Unplug /></IconAction>
        <IconAction label="删除" className="text-destructive" disabled={!enabled || Boolean(busy)} onClick={() => {
          if (window.confirm(`删除连接器 ${item.name}？已安装到工作区的文件需自行清理。`)) void run(`${item.id}:delete`, async () => { await connectorApi.delete(item.id); await refresh(); setNotice('连接器已删除。'); });
        }}><Trash2 /></IconAction>
      </div>
      {(tools[item.id] ?? item.tools).length > 0 && <details><summary className="cursor-pointer text-sm">可用工具（{(tools[item.id] ?? item.tools).length}）</summary><ul className="mt-3 space-y-3">{(tools[item.id] ?? item.tools).map(tool => <li key={tool.name} className="rounded-lg bg-muted/50 p-3"><p className="break-all font-mono text-xs">{tool.name}</p><p className="mt-1 text-sm text-muted-foreground">{tool.description}</p></li>)}</ul></details>}
    </section>)}
  </div></div>;
}

function IconAction({ label, ...props }: ComponentProps<typeof Button> & { label: string }) {
  return <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="icon-sm" aria-label={label} title={label} {...props} /></TooltipTrigger><TooltipContent>{label}</TooltipContent></Tooltip>;
}
