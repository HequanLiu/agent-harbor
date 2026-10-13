import assert from 'node:assert/strict';
import test from 'node:test';
import { mesDraftId, mesDraftSnapshot, connectorDraftRoute } from '../src/lib/mes-draft-link.ts';
const draft = { draft_id: 'draft_123', revision: 2, status: 'editing', payload: { mode: 'create' } };
test('card receives the validated draft snapshot from plain and structured results', () => {
  assert.deepEqual(mesDraftSnapshot('mes_order_draft_create', JSON.stringify(draft), 'success'), draft);
  assert.deepEqual(mesDraftSnapshot('mes_order_draft_get', { structuredContent: draft }, 'success'), draft);
  assert.equal(mesDraftSnapshot('mes_order_draft_get', draft, 'error'), null);
  assert.equal(mesDraftSnapshot('mes_order_draft_get', { ...draft, revision: 0 }, 'success'), null);
  assert.equal(mesDraftSnapshot('mes_order_draft_get', { ...draft, payload: null }, 'success'), null);
});
test('links only successful recognized MES draft tool responses', () => {
  assert.equal(mesDraftId('mcp__harbor_connector_abc__mes_order_draft_create', JSON.stringify(draft), 'success'), 'draft_123');
  assert.equal(mesDraftId('mes_order_draft_get', { structuredContent: draft }, 'success'), 'draft_123');
  for (const [name, output, state] of [
    ['some_tool', draft, 'success'], ['mes_order_search', draft, 'success'],
    ['mes_order_draft_get', draft, 'error'], ['mes_order_draft_get', { id: 'order_1' }, 'success'],
    ['mes_order_draft_get', { ...draft, status: 'something_else' }, 'success'],
    ['mes_order_draft_get', { ...draft, draft_id: '../escape' }, 'success'],
    ['mes_order_draft_get', 'not JSON', 'success'],
  ]) assert.equal(mesDraftId(name, output, state), null);
});
test('navigation uses only the matching local route returned by the server', () => {
  assert.equal(connectorDraftRoute({ connector_id: 'abc', url: '/connectors/abc/orders/draft_123' }, 'draft_123'), '/connectors/abc/orders/draft_123');
  for (const url of ['https://evil.test', '//evil.test', '/connectors/abc/orders/another']) {
    assert.throws(() => connectorDraftRoute({ connector_id: 'abc', url }, 'draft_123'));
  }
});
