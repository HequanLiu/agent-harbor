const record = (value: unknown): Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const idPattern = /^[A-Za-z0-9_-]{1,100}$/;
export interface MesDraft {
  draft_id: string; revision: number; status: string; payload: Record<string, unknown>;
  preview?: { content_hash: string; issues: { field_path: string; message: string; severity: string }[] };
  operation_id?: string; result?: { orderId?: string };
}
export const mesDraftStatuses: Record<string, string> = {
  editing: '编辑中', ready: '待确认', confirmed: '已确认', submitting: '提交中',
  unknown: '正在核对提交结果', committed: '已录入 MES', failed: '提交失败', cancelled: '已取消',
};
export function mesDraftSnapshot(toolName: string, output: unknown, state?: string): MesDraft | null {
  if (state !== 'success' || !/^(?:mcp__[^\s]+__)?mes_order_(?:draft_(?:create|get|patch|validate|cancel)|commit|operation_get)$/.test(toolName)) return null;
  let value = output;
  if (typeof value === 'string') { try { value = JSON.parse(value); } catch { return null; } }
  const envelope = record(value);
  const draft = record(envelope.structuredContent ?? value);
  const id = draft.draft_id ?? draft.id;
  if (typeof id !== 'string' || !idPattern.test(id) || !Number.isInteger(draft.revision) || Number(draft.revision) < 1) return null;
  if (!['editing', 'ready', 'confirmed', 'failed', 'submitting', 'unknown', 'committed', 'cancelled'].includes(String(draft.status))) return null;
  if (!['create', 'update'].includes(String(record(draft.payload).mode))) return null;
  return { ...draft, draft_id: id } as unknown as MesDraft;
}
export function mesDraftId(toolName: string, output: unknown, state?: string): string | null {
  return mesDraftSnapshot(toolName, output, state)?.draft_id ?? null;
}
export function connectorDraftRoute(value: unknown, draftId: string): string {
  const result = record(value);
  if (typeof result.connector_id !== 'string' || !idPattern.test(result.connector_id) || !idPattern.test(draftId)
    || result.url !== `/connectors/${result.connector_id}/orders/${draftId}`) throw new Error('服务返回了无效的草稿地址');
  return result.url as string;
}
