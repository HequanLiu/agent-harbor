import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { SourceAssistant } from './SourceAssistant';
import { client } from '@/api/client';
import { apiBaseUrl, apiFetch } from '@/lib/desktop';
import { mesDraftStatuses, type MesDraft as Draft } from '@/lib/mes-draft-link';
import { mergeUploadedPayload, sourceUploadError, type PicturePath } from '@/lib/order-upload';

interface Schema { $ref?: string; $defs?: Record<string, Schema>; anyOf?: Schema[]; type?: string; properties?: Record<string, Schema>; items?: Schema; enum?: string[]; default?: unknown; title?: string }
interface Source { asset_id: string; filename: string; media_type: string }
const labels: Record<string, string> = {
  order: '订单信息', style: '款式', pos: 'PO 明细', bom: 'BOM 物料', colors: '颜色', sizes: '尺码', name: '名称',
  style_num: '款号', style_name: '款名', customer_id: '客户', customer_name_input: '客户原文', due_date: '交期', order_type: '订单类型',
  picture_asset_id: '款式图', per_package_count: '每包件数', target_production: '目标产量', pre_schedule: '排期备注', po_num: 'PO 编号',
  quantities: '颜色尺码数量', color_key: '款式颜色', size_key: '款式尺码', count: '数量', material_type: '物料类型', material_name: '物料名称',
  specs: '规格', unit: '用量单位', unit_consume: '单耗', loss_rate: '损耗率 %', unit_price: '单价', purchase_unit: '采购单位', quantity: '采购数量',
  supplier_id: '供应商', is_main: '主料', is_need_cut: '需要裁剪', is_distinguish_color: '区分颜色', marking_type: '唛架类型', width: '幅宽',
  weight: '克重', remark: '备注', is_sew_aux: '车缝辅料', color_mappings: '适用颜色', material_color: '物料颜色', size_mappings: '适用尺码', expected_total: '订单预期总数',
  formal: '正式订单', sample: '样品订单', fabric: '面料', accessory: '辅料', other: '其他费用',
};
const control = 'w-full rounded-md border bg-background px-3 py-2 text-sm disabled:opacity-60';
const button = 'rounded-md border px-4 py-2 text-sm hover:bg-muted disabled:opacity-50';
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
function resolve(schema: Schema, root: Schema): Schema {
  if (schema.$ref) return resolve(root.$defs?.[schema.$ref.split('/').pop()!] ?? {}, root);
  if (schema.anyOf) return resolve(schema.anyOf.find(s => s.type !== 'null') ?? {}, root);
  return schema;
}
function initial(schema: Schema, root: Schema, key = ''): unknown {
  schema = resolve(schema, root);
  if (key === 'row_key') return crypto.randomUUID();
  if (schema.default !== undefined) return schema.default;
  if (schema.type === 'object') return Object.fromEntries(Object.entries(schema.properties ?? {}).map(([k, s]) => [k, initial(s, root, k)]));
  if (schema.type === 'array') return [];
  if (schema.type === 'boolean') return false;
  return null;
}
function Reference({ value, onChange, kind, base, disabled }: { value: unknown; onChange: (v: unknown) => void; kind: string; base: string; disabled: boolean }) {
  const [query, setQuery] = useState('');
  const [options, setOptions] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState('');
  async function search() {
    try { const result = await client.get<{ items: { id: string; name: string }[] }>(`${base}/references`, { kind, q: query }); setOptions(result.items); setError(''); }
    catch { setError('查询失败，请检查连接与权限'); }
  }
  return <div className="space-y-2"><div className="flex gap-2"><input className={control} aria-label="搜索名称" value={query} disabled={disabled} onChange={e => setQuery(e.target.value)} placeholder="按名称查询" /><button className={button} disabled={disabled} type="button" onClick={() => void search()}>查询</button></div>
    <select className={control} disabled={disabled} value={String(value ?? '')} onChange={e => onChange(e.target.value || null)}><option value="">请选择</option>{value && !options.some(o => o.id === value) ? <option value={String(value)}>当前：{String(value)}</option> : null}{options.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select>{error && <p role="alert">{error}</p>}</div>;
}
interface FieldProps { schema: Schema; root: Schema; value: unknown; onChange: (v: unknown) => void; field: string; payload: Record<string, unknown>; base: string; disabled: boolean; path: PicturePath; onUploadPicture: (file: File, path: PicturePath) => Promise<void> }
function Field({ schema, root, value, onChange, field, payload, base, disabled, path, onUploadPicture }: FieldProps) {
  const s = resolve(schema, root), title = labels[field] ?? field;
  if (['row_key', 'existing_id'].includes(field)) return null;
  const nested = (key: string, child: Schema, v: unknown, change: (v: unknown) => void, segment: string | number = key) => <Field key={key} schema={child} root={root} value={v} onChange={change} field={key} payload={payload} base={base} disabled={disabled} path={[...path, segment]} onUploadPicture={onUploadPicture} />;
  if (s.type === 'object') return <fieldset className="space-y-4 rounded-lg border p-4"><legend className="px-2 font-semibold">{title}</legend><div className="grid gap-4 sm:grid-cols-2">{Object.entries(s.properties ?? {}).map(([k, child]) => nested(k, child, object(value)[k], v => onChange({ ...object(value), [k]: v })))}</div></fieldset>;
  if (s.type === 'array') { const rows = Array.isArray(value) ? value : []; return <section className="col-span-full space-y-3"><div className="flex items-center justify-between"><h3 className="font-semibold">{title}</h3><button type="button" className={button} disabled={disabled} onClick={() => onChange([...rows, initial(s.items ?? {}, root)])}>添加{title}</button></div>{rows.map((row, i) => <div className="rounded-lg border p-3" key={String(object(row).row_key ?? i)}>{nested(`${field} ${i + 1}`, s.items ?? {}, row, v => onChange(rows.map((r, at) => at === i ? v : r)), i)}</div>)}</section>; }
  let input;
  const style = object(payload.style);
  const choices = ['color_key', 'size_key'].includes(field) ? ((style[field === 'color_key' ? 'colors' : 'sizes'] ?? []) as Record<string, unknown>[]).map(x => ({ id: String(x.row_key), name: String(x.name ?? '未命名') })) : null;
  if (field === 'picture_asset_id') input = <input className={control} type="text" disabled={disabled} value={String(value ?? '')} placeholder="请输入图片资产 ID" onChange={e => onChange(e.target.value.trim() || null)} />;
  else if (field === 'customer_id' || field === 'supplier_id') input = <Reference value={value} onChange={onChange} kind={field === 'customer_id' ? 'customer' : 'supplier'} base={base} disabled={disabled} />;
  else if (choices || s.enum) input = <select className={control} value={String(value ?? '')} disabled={disabled} onChange={e => onChange(e.target.value || null)}><option value="">请选择</option>{choices ? <>{value && !choices.some(c => c.id === value) ? <option value={String(value)}>已登记图片</option> : null}{choices.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</> : s.enum?.map(v => <option key={v} value={v}>{labels[v] ?? v}</option>)}</select>;
  else if (s.type === 'boolean') input = <input type="checkbox" checked={Boolean(value)} disabled={disabled} onChange={e => onChange(e.target.checked)} />;
  else input = <input className={control} disabled={disabled} type={field === 'due_date' ? 'date' : s.type === 'integer' ? 'number' : 'text'} min={s.type === 'integer' ? 0 : undefined} step={s.type === 'integer' ? 1 : undefined} value={String(value ?? '')} onChange={e => onChange(e.target.value === '' ? null : s.type === 'integer' ? Number(e.target.value) : e.target.value)} />;
  if (field === 'picture_asset_id') return <div className="space-y-2 text-sm">
    <label className="flex flex-col gap-2">{title}资产 ID{input}</label>
    <p className="text-xs text-muted-foreground">填写已上传图片的资产 ID，点击“保存草稿”保存。</p>
  </div>;
  return <label className="flex flex-col gap-2 text-sm">{title}{input}</label>;
}

export default function OrderEditorPage() {
  const { connectorId = '', draftId } = useParams();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  return <OrderEditorSession key={`${connectorId}/${draftId ?? 'new'}`} connectorId={connectorId} draftId={draftId}
    initialOrderId={search.get('orderId') ?? ''} mode={search.get('mode') ?? ''}
    onCreated={next => navigate(`/connectors/${connectorId}/orders/${next.draft_id}`, { replace: true })} />;
}

interface OrderEditorProps {
  connectorId: string; draftId?: string; embedded?: boolean; initialOrderId?: string; mode?: string;
  onCreated?: (draft: Draft) => void;
  onDraftChange?: (draft: Draft) => void;
  onEditingChange?: (state: { dirty: boolean; busy: boolean }) => void;
}
export function OrderEditorSession({ connectorId, draftId, embedded = false, initialOrderId = '', mode,
  onCreated, onDraftChange, onEditingChange }: OrderEditorProps) {
  const base = `/harbor/connectors/${encodeURIComponent(connectorId)}`;
  const [schema, setSchema] = useState<Schema>();
  const [draft, setDraft] = useState<Draft>();
  const [payload, setPayload] = useState<Record<string, unknown>>({});
  const [dirty, setDirty] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [reviewed, setReviewed] = useState<string[]>([]), [confirmed, setConfirmed] = useState(false);
  const [orderId, setOrderId] = useState(initialOrderId);
  useEffect(() => { if (draft) onDraftChange?.(draft); }, [draft, onDraftChange]);
  useEffect(() => { onEditingChange?.({ dirty, busy }); }, [dirty, busy, onEditingChange]);
  function accept(next: Draft) { setDraft(next); setPayload(next.payload); setDirty(false); setReviewed([]); setConfirmed(false); }
  async function run(work: () => Promise<void>) { setBusy(true); setError(''); try { await work(); } catch (e) { setError(e instanceof Error ? e.message : '操作失败'); } finally { setBusy(false); } }
  useEffect(() => {
    let active = true;
    void client.get<Schema>(`${base}/schema`).then(s => { if (active) setSchema(s); }).catch(() => { if (active) setError('无法加载订单表单，请检查连接器授权。'); });
    if (draftId) void client.stream(`${base}/drafts/${encodeURIComponent(draftId)}/events`).then(r => r.text()).then(text => {
      for (const line of text.split('\n')) if (line.startsWith('data:')) { const event = JSON.parse(line.slice(5)) as { type: string; snapshot?: { draft: Draft } }; if (active && event.type === 'STATE_SNAPSHOT' && event.snapshot?.draft) accept(event.snapshot.draft); }
    }).catch(() => { if (active) setError('无法恢复草稿，请检查连接器或草稿是否已过期。'); });
    return () => { active = false; };
  }, [base, draftId]);
  async function create() { await run(async () => { const next = await client.post<Draft>(`${base}/drafts`, orderId ? { mode: 'update', target_order_id: orderId } : {}); accept(next); onCreated?.(next); }); }
  async function save() { if (!draft) return; await run(async () => { const changes = Object.fromEntries(['order', 'style', 'pos', 'bom', 'expected_total'].map(k => [k, payload[k]])); accept(await client.patch<Draft>(`${base}/drafts/${draft.draft_id}`, { expected_revision: draft.revision, changes: { ...changes, reviewed_fields: reviewed } })); }); }
  async function action(name: string) { if (!draft) return; await run(async () => accept(await client.post<Draft>(`${base}/drafts/${draft.draft_id}/${name}`, { revision: draft.revision, content_hash: draft.preview?.content_hash }))); }
  async function upload(file: File, picturePath?: PicturePath) { if (!draft || busy) return; await run(async () => {
    if (picturePath && (!/\.(png|jpe?g|webp)$/i.test(file.name) || (file.type && !['image/png', 'image/jpeg', 'image/webp'].includes(file.type)))) throw new Error('款式图请选择 PNG、JPG 或 WebP 图片');
    if (picturePath && file.size > 10 * 1024 * 1024) throw new Error('款式图不能超过 10 MiB');
    const form = new FormData(); form.append('file', file);
    const response = await apiFetch(new URL(`${base.replace(/^\//, '')}/sources`, apiBaseUrl()), { method: 'POST', credentials: 'same-origin', headers: { 'X-Tenant-ID': sessionStorage.getItem('harbor_tenant') ?? '' }, body: form });
    if (response.status === 401) window.dispatchEvent(new Event('harbor:unauthorized'));
    if (!response.ok) throw new Error(sourceUploadError(await response.json().catch(() => ({})), response.status));
    const source = await response.json() as Source;
    const next = await client.post<Draft>(`${base}/drafts/${draft.draft_id}/sources`, { revision: draft.revision, asset_id: source.asset_id });
    setDraft(next);
    setPayload(mergeUploadedPayload(next.payload, dirty ? payload : next.payload, picturePath ? { path: picturePath, assetId: source.asset_id } : undefined));
    setDirty(dirty || Boolean(picturePath));
    if (!dirty) setReviewed([]);
    setConfirmed(false);
  }); }
  const immutable = ['committed', 'unknown', 'submitting', 'cancelled'].includes(draft?.status ?? '');
  const evidence = (Array.isArray(payload.evidence) ? payload.evidence : []) as { field_path: string; raw_text?: string; needs_review: boolean }[];
  const sources = (Array.isArray(payload.sources) ? payload.sources : []) as Source[];
  return <section className={`mx-auto w-full max-w-5xl space-y-6 p-4 sm:p-6${embedded ? '' : ' overflow-auto'}`}>{!embedded && <Link className="text-sm underline" to="/connectors">返回连接器</Link>}
    <header>{!embedded && <><p className="text-sm text-muted-foreground">MES 订单工作台</p><h1 className="text-2xl font-semibold">{(draft?.payload.mode === 'update' || (!draft && mode === 'update')) ? '修改订单' : '新增订单'}</h1></>}<p className="text-sm text-muted-foreground">上传订单图片或文件后交给助手识别，也可以直接填写。保存草稿不会写入正式订单。</p></header>
    {error && <p role="alert" className="rounded-lg border border-destructive p-4 text-sm">{error}</p>}
    {!draft && draftId ? <p role="status">{error ? (embedded ? '草稿未能恢复，请关闭后重新打开重试。' : '草稿未能恢复，请返回连接器后重试。') : '正在恢复订单草稿…'}</p> : !draft ? <section className="space-y-3 rounded-lg border p-5"><label className="block text-sm">修改已有订单时输入订单 ID，留空则新增<input className={control} value={orderId} onChange={e => setOrderId(e.target.value)} inputMode="numeric" /></label><button className={button} disabled={busy || !schema} onClick={() => void create()}>{orderId ? '加载订单快照' : '建立空白草稿'}</button></section> : <>
      <p className="text-sm">草稿版本 {draft.revision} · {mesDraftStatuses[draft.status] ?? draft.status}{dirty ? ' · 有未保存修改' : ''}</p>
      <section className="space-y-3 rounded-lg border p-4"><h2 className="font-semibold">订单来源</h2><label className="block text-sm">上传图片、PDF、XLSX 或文本（20 MiB 内，图片 10 MiB 内）<input className="mt-2 block" type="file" accept=".png,.jpg,.jpeg,.webp,.pdf,.xlsx,.txt,.csv" disabled={busy || immutable} onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file); e.target.value = ''; }} /></label>
        {sources.map(s => <div key={s.asset_id} className="rounded border p-3 text-sm"><p>{s.filename}</p><SourceAssistant connectorId={connectorId} draftId={draft.draft_id} assetId={s.asset_id} disabled={busy || immutable || dirty} /><button className="mt-2 underline" onClick={() => void navigator.clipboard.writeText(`请用 mes_order_source_read 读取来源 ${s.asset_id}，把识别结果填入草稿 ${draft.draft_id}，保留来源证据，完成后让我在订单工作台确认。`)}>复制给助手的识别指令</button></div>)}
      </section>
      {schema && <div className="space-y-5">{['order', 'style', 'pos', 'bom', 'expected_total'].map(key => <Field key={key} schema={schema.properties?.[key] ?? {}} root={schema} value={payload[key]} field={key} payload={payload} base={base} disabled={busy || immutable} path={[key]} onUploadPicture={upload} onChange={v => { setPayload({ ...payload, [key]: v }); setDirty(true); setConfirmed(false); }} />)}</div>}
      {evidence.length > 0 && <section className="space-y-3 rounded-lg border p-4"><h2 className="font-semibold">识别结果核对</h2>{evidence.map((e, i) => <label key={i} className="flex gap-3 text-sm"><input type="checkbox" disabled={busy || immutable || !e.needs_review} checked={!e.needs_review || reviewed.includes(e.field_path)} onChange={event => { setReviewed(event.target.checked ? [...reviewed, e.field_path] : reviewed.filter(f => f !== e.field_path)); setDirty(true); setConfirmed(false); }} /><span>{e.field_path}：{e.raw_text ?? '请对照来源文件核对'}</span></label>)}</section>}
      {draft.preview?.issues.map((issue, i) => <p key={i} role="status" className="rounded border p-3 text-sm">{issue.field_path}：{issue.message}</p>)}
      {draft.status === 'ready' && !dirty && <label className="flex gap-3 rounded-lg border p-4"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} /><span>我已核对以上订单、款式、PO 数量和 BOM，确认将当前版本写入 MES。</span></label>}
      <footer className="sticky bottom-0 flex flex-wrap gap-3 border-t bg-background py-4"><button className={button} disabled={busy || immutable || !dirty} onClick={() => void save()}>保存草稿</button><button className={button} disabled={busy || immutable || dirty} onClick={() => void action('validate')}>校验并预览</button><button className={`${button} bg-primary text-primary-foreground`} disabled={busy || dirty || !confirmed || draft.status !== 'ready'} onClick={() => void action('confirm')}>确认并录入</button>
        {['unknown', 'submitting'].includes(draft.status) && draft.operation_id && <button className={button} disabled={busy} onClick={() => void run(async () => accept(await client.get<Draft>(`${base}/operations/${draft.operation_id}`)))}>核对提交结果</button>}
        {!immutable && <button className={button} disabled={busy} onClick={() => void action('cancel')}>取消草稿</button>}
      </footer>
      {draft.status === 'committed' && <p role="status" className="rounded-lg border p-4">订单已成功录入 MES{draft.result?.orderId ? `，订单 ID：${draft.result.orderId}` : ''}。</p>}
    </>}
  </section>;
}
