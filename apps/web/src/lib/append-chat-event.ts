import type { AgentEvent } from '@agentscope-ai/agentscope/event';
import { appendEvent, type Msg } from '@agentscope-ai/agentscope/message';

/** Preserve host-only hint metadata until the upstream SDK supports it. */
export function appendChatEvent(message: Msg, event: AgentEvent): void {
  appendEvent(message, event);
  if (event.type === 'HINT_BLOCK') {
    const block = message.content.find(b => b.type === 'hint' && b.id === event.block_id);
    if (block) Object.assign(block, { metadata: event.metadata ?? {} });
  }
}
