import assert from 'node:assert/strict';
import test from 'node:test';
import { HarborClient, ApiError } from '../src/api/client.ts';

test('transport invokes fetch without a client receiver and sends bearer on SSE', async () => {
  const client = new HarborClient('https://example.test/', async function (url, options) {
    assert.equal(this, undefined);
    assert.equal(url, 'https://example.test/sessions/session/stream?agent_id=agent');
    assert.equal(options.headers.Authorization, 'Bearer test-token');
    assert.equal(options.headers['X-Tenant-ID'], 'tenant');
    assert.equal(options.headers.Accept, 'text/event-stream');
    assert.equal(options.credentials, 'omit');
    return new Response('data: {}\n\n');
  });
  client.setSession('test-token', 'tenant');
  const result = await client.stream('agent', 'session', new AbortController().signal);
  assert.ok(result.body);
});

test('401 clears a current session but a late response cannot clear a newer login', async () => {
  let complete;
  let count = 0;
  const client = new HarborClient('https://example.test', () => new Promise(resolve => { complete = resolve; }));
  client.setUnauthorized(() => count++);
  client.setSession('old');
  const pending = client.me();
  client.setSession('new');
  complete(new Response('{}', { status: 401 }));
  await assert.rejects(pending, ApiError);
  assert.equal(count, 0);
  const current = client.me();
  complete(new Response('{}', { status: 401 }));
  await assert.rejects(current, ApiError);
  assert.equal(count, 1);
});

test('failed message submission is never retried automatically', async () => {
  let count = 0;
  const client = new HarborClient('https://example.test', async () => { count++; throw new TypeError('offline'); });
  await assert.rejects(client.send('agent', 'session', { role: 'user', content: [] }), ApiError);
  assert.equal(count, 1);
});

import { hasPendingTool } from '../src/core/messages.ts';
test('only the latest assistant message can park a resumed conversation', () => {
  const parked = {id: 'old', role: 'assistant', content: [{type: 'tool_call', state: 'asking'}]};
  assert.equal(hasPendingTool([parked]), true);
  assert.equal(hasPendingTool([parked, {id: 'new', role: 'assistant', content: [{type: 'text', text: 'Done'}]}]), false);
});

import { applyEvent, reconcileHistory } from '../src/core/messages.ts';
test('bounded replay without REPLY_START still renders text and settles from persisted history', () => {
  let state = {messages: [], running: true, pending: false, seen: new Set()};
  state = applyEvent(state, {type: 'TEXT_BLOCK_DELTA', reply_id: 'reply', block_id: 'block', delta: 'tail'});
  assert.equal(state.messages[0].content[0].text, 'tail');
  state = applyEvent(state, {type: 'REPLY_END', reply_id: 'reply'});
  const complete = {id: 'reply', role: 'assistant', content: [{id: 'block', type: 'text', text: 'complete reply tail'}]};
  state = reconcileHistory(state, {messages: [complete], is_running: false, has_more: false});
  assert.equal(state.messages[0].content[0].text, 'complete reply tail');
  assert.equal(state.running, false);
});
test('history reconciliation restores completion missed between history and subscription', () => {
  const earlier = {id: 'earlier', role: 'user', content: []};
  const current = {id: 'current', role: 'user', content: []};
  const reply = {id: 'reply', role: 'assistant', content: [{type: 'text', text: 'Finished in gap'}]};
  const state = reconcileHistory({messages: [earlier, current], running: true, pending: false, seen: new Set()}, {messages: [current, reply], is_running: false, has_more: true});
  assert.deepEqual(state.messages, [earlier, current, reply]);
  assert.equal(state.running, false);
});
