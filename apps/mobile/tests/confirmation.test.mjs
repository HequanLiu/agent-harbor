import test from 'node:test';
import assert from 'node:assert/strict';
import { applyEvent, getConfirmations, reconcileHistory } from '../src/core/messages.ts';
import { HarborClient } from '../src/api/client.ts';
const empty = () => ({ messages: [], pending: false, running: false, seen: new Set() });
const call = { type: 'tool_call', id: 'call', name: 'fixture_tool', input: '{"value":1}', state: 'asking', suggested_rules: [{ tool_name: 'fixture_tool', rule_content: '*' }] };
test('confirmation survives missing start, duplicate SSE and history restoration; results clear only the matching call', () => {
  const event = { type: 'REQUIRE_USER_CONFIRM', id: 'e', reply_id: 'reply', tool_calls: [call, {...call, id:'second'}] };
  let state = applyEvent(empty(), event);
  state = applyEvent(state, event);
  assert.equal(getConfirmations(state).length, 2);
  assert.deepEqual(getConfirmations(state)[0].toolCall, call);
  state = reconcileHistory(empty(), { messages: state.messages, is_running: false, has_more: false });
  assert.equal(state.pending, true);
  state = applyEvent(state, { type: 'TOOL_RESULT_START', reply_id: 'reply', tool_call_id: 'call' });
  assert.equal(getConfirmations(state).length, 1);
  assert.equal(getConfirmations(state)[0].toolCall.id, 'second');
  state = applyEvent(state, { type: 'REPLY_END', reply_id: 'reply' });
  assert.equal(getConfirmations(state).length, 0);
});
test('external execution and old replies cannot be approved', () => {
  let state = applyEvent(empty(), { type:'REQUIRE_EXTERNAL_EXECUTION', reply_id:'reply', tool_calls:[call] });
  assert.equal(state.pending, true);
  assert.equal(getConfirmations(state).length, 0);
  state = applyEvent(empty(), { type:'REQUIRE_USER_CONFIRM', reply_id:'reply', tool_calls:[call] });
  state.messages.push({ id:'new', role:'user', content:[] });
  assert.equal(getConfirmations(state).length, 0);
});
test('team confirmation deduplicates and clears via leader notifications', () => {
  const event = { type:'CUSTOM', name:'subagent_require_user_confirm', value:{ worker_session_id:'worker', worker_agent_name:'Worker', reply_id:'child-reply', event:{ tool_calls:[call] } } };
  let state = applyEvent(applyEvent(empty(), event), event);
  assert.equal(getConfirmations(state).length, 1);
  assert.equal(getConfirmations(state)[0].replyId, 'child-reply');
  state = applyEvent(state, {...event, name:'subagent_user_confirm_result'});
  assert.equal(getConfirmations(state).length, 0);
});
test('confirmation posts desktop-compatible payload with bearer and tenant, including rejection and rules', async () => {
  for (const approved of [true, false]) {
    const input = { type:'USER_CONFIRM_RESULT', id:'event', created_at:new Date().toISOString(), reply_id:'reply', confirm_results:[{ confirmed:approved, tool_call:call, rules:approved ? call.suggested_rules : null }] };
    const client = new HarborClient('https://example.test/', async (url, options) => {
      assert.equal(url, 'https://example.test/chat/');
      assert.equal(options.headers.Authorization, 'Bearer token');
      assert.equal(options.headers['X-Tenant-ID'], 'tenant');
      assert.deepEqual(JSON.parse(options.body), { agent_id:'agent', session_id:'session', input });
      return new Response('{}');
    });
    client.setSession('token','tenant');
    await client.send('agent', 'session', input);
  }
});
