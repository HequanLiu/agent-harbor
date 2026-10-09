import type { AgentEvent, History, Message, Confirmation, ToolCall } from "./types";
export interface ChatState {
  messages: Message[];
  running: boolean;
  pending: boolean;
  teamConfirmations?: Confirmation[];
  seen: Set<string>;
  error?: string;
}
export function applyEvent(state: ChatState, event: AgentEvent): ChatState {
  if (event.id && state.seen.has(event.id)) return state;
  const seen = new Set(state.seen);
  if (event.id) seen.add(event.id);
  if (seen.size > 4000) seen.delete(seen.values().next().value!);
  let next = { ...state, seen };
  if (event.type === "CUSTOM") {
    const value = event.value;
    if (value && ["subagent_require_user_confirm", "subagent_user_confirm_result"].includes(event.name || "")) {
      const remaining = (next.teamConfirmations || []).filter((c) => c.workerSession !== value.worker_session_id || c.replyId !== value.reply_id);
      next.teamConfirmations = event.name === "subagent_require_user_confirm" && value.event_type !== "require_external_execution"
        ? [...remaining, ...(value.event?.tool_calls || []).map((toolCall) => ({ replyId: value.reply_id, toolCall, workerSession: value.worker_session_id, workerName: value.worker_agent_name }))]
        : remaining;
    }
    return next;
  }
  const id = event.reply_id;
  if (!id) return next;
  if (event.type === "REPLY_START") {
    next = { ...next, running: true, pending: false, error: undefined };
    if (!next.messages.some((m) => m.id === id))
      next.messages = [
        ...next.messages,
        { id, role: event.role || "assistant", name: event.name, content: [] },
      ];
  }
  if (event.type.startsWith("TEXT_BLOCK_")) {
    // Replay is bounded: the start frame may already have been evicted.
    if (!next.messages.some((message) => message.id === id)) {
      next = { ...next, running: true, messages: [...next.messages, { id, role: "assistant", content: [] }] };
    }
    next.messages = next.messages.map((message) => {
      if (message.id !== id) return message;
      const content = [...message.content];
      const index = content.findIndex((b) => b.id === event.block_id);
      const previous = index >= 0 ? content[index].text || "" : "";
      const text =
        event.type === "TEXT_BLOCK_START"
          ? ""
          : event.type === "TEXT_BLOCK_END"
            ? (event.text ?? previous)
            : previous + (event.delta || "");
      const block = { id: event.block_id, type: "text", text };
      if (index < 0) content.push(block);
      else content[index] = block;
      return { ...message, content };
    });
  }
  if (["REQUIRE_USER_CONFIRM", "REQUIRE_EXTERNAL_EXECUTION"].includes(event.type)) {
    const calls = (event.tool_calls || []).map((call) => ({ ...call, state: event.type === "REQUIRE_USER_CONFIRM" ? "asking" : "submitted" }));
    if (!next.messages.some((m) => m.id === id)) {
      next.messages = [...next.messages, { id, role: "assistant", content: [] }];
    }
    next.messages = next.messages.map((m) => m.id !== id ? m : {
      ...m, content: [...m.content.filter((b) => !calls.some((call) => call.id === b.id)), ...calls],
    });
    next = { ...next, running: true, pending: true };
  }
  if (["TOOL_RESULT_START", "TOOL_RESULT_END"].includes(event.type)) {
    next.messages = next.messages.map((m) => m.id !== id ? m : {
      ...m, content: m.content.map((b) => b.type === "tool_call" && b.id === event.tool_call_id ? { ...b, state: "finished" } : b),
    });
    next.pending = hasPendingTool(next.messages);
  }
  if (event.type === "REPLY_END")
    next = {
      ...next,
      messages: next.messages.map((m) => m.id !== id ? m : { ...m, content: m.content.map((b) => b.type === "tool_call" ? { ...b, state: "finished" } : b) }),
      running: false,
      pending: false,
      error:
        event.error?.message ||
        (event.finished_reason === "error"
          ? "生成失败，请稍后重试。"
          : undefined),
    };
  return next;
}
export function hasPendingTool(messages: Message[]): boolean {
  const latest = messages[messages.length - 1];
  return latest?.role === "assistant" && latest.content.some(
    (block) => block.type === "tool_call" && ["asking", "submitted"].includes(block.state || ""),
  ) || false;
}

/** Replace the authoritative latest page while retaining previously loaded older pages. */
export function reconcileHistory(state: ChatState, history: History): ChatState {
  const first = state.messages.findIndex((message) => message.id === history.messages[0]?.id);
  const pending = hasPendingTool(history.messages);
  return {
    ...state,
    messages: [...(first > 0 ? state.messages.slice(0, first) : []), ...history.messages],
    running: history.is_running || pending,
    pending,
  };
}

export function getConfirmations(state: ChatState): Confirmation[] {
  const latest = state.messages[state.messages.length - 1];
  const calls = latest?.role === "assistant" ? latest.content.filter((b): b is ToolCall => b.type === "tool_call" && b.state === "asking" && !!b.id && "name" in b && "input" in b).map((toolCall) => ({ replyId: latest.id, toolCall })) : [];
  return [...calls, ...(state.teamConfirmations || [])];
}
export function confirmationKey(c: Confirmation): string {
  return JSON.stringify([c.workerSession || "", c.replyId, c.toolCall.id]);
}
