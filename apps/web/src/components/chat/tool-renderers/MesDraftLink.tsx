import { useState } from 'react';
import { useCallback, useRef } from 'react';
import { ClipboardList } from 'lucide-react';

import { connectorApi } from '@/api/connectors';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { connectorDraftRoute, mesDraftStatuses, type MesDraft } from '@/lib/mes-draft-link';
import { OrderEditorSession } from '@/pages/connectors/OrderEditor';

const fields = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const label = (value: unknown) => (typeof value === 'string' && value) || typeof value === 'number' ? String(value) : '待填写';

export function MesDraftLink({ draftId, initialDraft }: { draftId: string; initialDraft?: MesDraft }) {
  const trigger = useRef<HTMLButtonElement>(null);
  const [draft, setDraft] = useState(initialDraft);
  const [connectorId, setConnectorId] = useState('');
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState({ dirty: false, busy: false });
  const [discard, setDiscard] = useState(false);
  const handleEditingChange = useCallback((state: { dirty: boolean; busy: boolean }) => {
    setEditing(state);
    if (!state.dirty) setDiscard(false);
  }, []);
  const current = draft && (!initialDraft || draft.revision >= initialDraft.revision) ? draft : initialDraft;
  const order = fields(current?.payload.order);
  const style = fields(current?.payload.style);
  const readOnly = ['committed', 'cancelled', 'unknown', 'submitting'].includes(current?.status ?? '');
  async function show() {
    setBusy(true); setError('');
    try {
      const result = await connectorApi.resolveDraft(draftId);
      connectorDraftRoute(result, draftId);
      setConnectorId(result.connector_id);
      setEditing({ dirty: false, busy: false });
      setDiscard(false);
      setOpen(true);
    } catch (e) { setError(e instanceof Error ? e.message : '无法打开草稿，请检查连接器授权'); }
    finally { setBusy(false); }
  }
  function changeOpen(next: boolean) {
    if (next || editing.busy) return;
    if (editing.dirty) { setDiscard(true); return; }
    setOpen(false);
  }
  return <div className="my-3 max-w-xl rounded-xl border bg-card p-4 text-card-foreground">
    <div className="flex items-start gap-3">
      <div className="rounded-lg bg-muted p-2"><ClipboardList className="size-5 text-muted-foreground" /></div>
      <div className="min-w-0 flex-1"><p className="font-medium">{current?.payload.mode === 'update' ? '修改订单草稿' : '订单草稿'}</p><p className="mt-1 text-xs text-muted-foreground" role="status">{mesDraftStatuses[current?.status ?? ''] ?? '待填写'}{current ? ` · 版本 ${current.revision}` : ''}</p></div>
    </div>
    <dl className="my-4 grid grid-cols-2 gap-3 text-sm">
      <div><dt className="text-xs text-muted-foreground">款号</dt><dd className="mt-1 break-words">{label(style.style_num ?? order.style_num)}</dd></div>
      <div><dt className="text-xs text-muted-foreground">客户</dt><dd className="mt-1 break-words">{label(order.customer_name_input ?? order.customer_id)}</dd></div>
      <div><dt className="text-xs text-muted-foreground">交期</dt><dd className="mt-1">{label(order.due_date)}</dd></div>
      <div><dt className="text-xs text-muted-foreground">PO 明细</dt><dd className="mt-1">{Array.isArray(current?.payload.pos) ? `${current.payload.pos.length} 条` : '待填写'}</dd></div>
    </dl>
    <Button ref={trigger} size="sm" variant="outline" disabled={busy} onClick={() => void show()}>{busy ? '正在加载草稿…' : readOnly ? '查看订单' : '填写订单'}</Button>
    {error && <p role="alert" className="mt-2 text-xs text-destructive">{error}</p>}
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogContent showCloseButton={!editing.busy} className="flex h-dvh max-h-dvh w-full max-w-full flex-col gap-0 rounded-none p-0 sm:h-[90dvh] sm:max-w-5xl sm:rounded-xl"
        onCloseAutoFocus={event => { event.preventDefault(); trigger.current?.focus(); }}
        onInteractOutside={event => event.preventDefault()}>
        <DialogHeader className="shrink-0 border-b px-5 py-4 pr-12">
          <DialogTitle>{current?.payload.mode === 'update' ? '修改订单' : '订单草稿'}</DialogTitle>
          <DialogDescription>填写并核对订单，完成后继续当前对话。</DialogDescription>
        </DialogHeader>
        {discard && <div role="alert" className="shrink-0 space-y-3 border-b bg-muted p-4">
          <p>还有未保存的修改。继续编辑并保存，或放弃这些修改后关闭。</p>
          <div className="flex gap-2"><Button size="sm" onClick={() => setDiscard(false)}>继续编辑</Button><Button size="sm" variant="outline" disabled={editing.busy} onClick={() => { setDiscard(false); setOpen(false); }}>放弃修改并关闭</Button></div>
        </div>}
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          {open && <OrderEditorSession key={`${connectorId}/${draftId}`} connectorId={connectorId} draftId={draftId} embedded onDraftChange={setDraft} onEditingChange={handleEditingChange} />}
        </div>
      </DialogContent>
    </Dialog>
  </div>;
}
