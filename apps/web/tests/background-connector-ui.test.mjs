import assert from 'node:assert/strict';
import test from 'node:test';
import { appendChatEvent } from '../src/lib/append-chat-event.ts';
import { connectorBinding } from '../src/lib/connector-app.ts';

test('SDK hint event preserves UI binding live and after JSON history round trip', () => {
  const binding = { binding_token: 'opaque', resource_uri: 'ui://mes/editor', tool_name: 'create' };
  const message = { id: 'r', name: 'Agent', role: 'assistant', content: [] };
  appendChatEvent(message, { type: 'HINT_BLOCK', reply_id: 'r', block_id: 'h',
    hint: 'Created draft', metadata: { connector_ui: binding } });
  assert.deepEqual(connectorBinding(message.content[0]), binding);
  assert.deepEqual(connectorBinding(JSON.parse(JSON.stringify(message)).content[0]), binding);
});
