import assert from 'node:assert/strict';
import test from 'node:test';
import { getBinding, parseNativeRequest, messageText } from '../src/connector-ui/protocol.ts';
import { applyEvent, reconcileHistory } from '../src/core/messages.ts';

test('background completion hint preserves UI binding in live messages and history', () => {
  const binding = { binding_token: 'opaque', resource_uri: 'ui://mes/editor', tool_name: 'create' };
  const event = { type: 'HINT_BLOCK', id: 'e', reply_id: 'r', block_id: 'h',
    hint: 'Created draft', metadata: { connector_ui: binding } };
  let state = applyEvent({ messages: [], running: false, pending: false, seen: new Set() }, event);
  assert.deepEqual(getBinding(state.messages[0].content[0]), binding);
  state = applyEvent(state, event);
  assert.equal(state.messages[0].content.length, 1);
  state = reconcileHistory(state, { messages: state.messages, is_running: false, has_more: false });
  assert.deepEqual(getBinding(state.messages[0].content[0]), binding);
});

test('native bridge requires instance nonce, session and approved method', () => {
  const request = { nonce: 'secret', sessionId: 's', id: '1', kind: 'rpc', payload: { method: 'tools/call' } };
  assert.ok(parseNativeRequest(JSON.stringify(request), 'secret', 's'));
  assert.equal(parseNativeRequest(JSON.stringify(request), 'other', 's'), null);
  assert.equal(parseNativeRequest(JSON.stringify(request), 'secret', 'other'), null);
  assert.equal(parseNativeRequest(JSON.stringify({ ...request, payload: { method: 'native/invoke' } }), 'secret', 's'), null);
  assert.equal(parseNativeRequest('null', 'secret', 's'), null);
  assert.throws(() => messageText({ content: [{ type: 'image' }] }));
  assert.equal(getBinding({ text: '{"connector_ui":{}}' }), null);
});
test('real SSE tool-result metadata and fallback text survive history reconciliation', () => {
  let state = { messages: [], running: false, pending: false, seen: new Set() };
  const base = { reply_id: 'r', tool_call_id: 't' };
  state = applyEvent(state, { ...base, type: 'TOOL_RESULT_START' });
  state = applyEvent(state, { ...base, type: 'TOOL_RESULT_TEXT_DELTA', delta: 'Created' });
  const binding = { binding_token: 'opaque', resource_uri: 'ui://crm/v1', tool_name: 'create' };
  state = applyEvent(state, { ...base, type: 'TOOL_RESULT_END', state: 'success', metadata: { connector_ui: binding } });
  assert.equal(state.messages[0].content[0].output, 'Created');
  assert.deepEqual(getBinding(state.messages[0].content[0]), binding);
  state = reconcileHistory(state, { messages: state.messages, is_running: false, has_more: false });
  assert.deepEqual(getBinding(state.messages[0].content[0]), binding);
});
