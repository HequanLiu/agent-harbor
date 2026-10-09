import { test } from "node:test";
import assert from "node:assert/strict";
import { readEvents } from "../src/core/sse.ts";
import { applyEvent } from "../src/core/messages.ts";

const stream = (chunks) =>
  new ReadableStream({
    start(c) {
      chunks.forEach((x) => c.enqueue(x));
      c.close();
    },
  });
test("SSE preserves UTF-8 split bytes, CRLF frames, comments and multi-line data", async () => {
  const bytes = new TextEncoder().encode(
    ': ping\r\ndata: {"type":"TEXT_BLOCK_DELTA",\r\ndata: "delta":"你好"}\r\n\r\n',
  );
  const events = [];
  for await (const event of readEvents(
    stream(Array.from(bytes, (b) => Uint8Array.of(b))),
  ))
    events.push(event);
  assert.deepEqual(events, [{ type: "TEXT_BLOCK_DELTA", delta: "你好" }]);
});
test("SSE reports malformed events instead of silently losing a reply", async () => {
  await assert.rejects(async () => {
    for await (const e of readEvents(
      stream([new TextEncoder().encode("data: invalid\n\n")]),
    ))
      void e;
  });
});
test("Replay replaces a partial history block and duplicate events are ignored", () => {
  let state = {
    messages: [
      {
        id: "r",
        role: "assistant",
        content: [{ id: "b", type: "text", text: "old" }],
      },
    ],
    running: true,
    pending: false,
    seen: new Set(),
  };
  for (const event of [
    { id: "s", type: "REPLY_START", reply_id: "r" },
    { id: "bs", type: "TEXT_BLOCK_START", reply_id: "r", block_id: "b" },
    {
      id: "d",
      type: "TEXT_BLOCK_DELTA",
      reply_id: "r",
      block_id: "b",
      delta: "你好",
    },
    {
      id: "d",
      type: "TEXT_BLOCK_DELTA",
      reply_id: "r",
      block_id: "b",
      delta: "你好",
    },
    { id: "end", type: "REPLY_END", reply_id: "r" },
  ])
    state = applyEvent(state, event);
  assert.equal(state.messages.length, 1);
  assert.equal(state.messages[0].content[0].text, "你好");
  assert.equal(state.running, false);
});
test("final text overrides deltas and tool confirmation stays interruptible", () => {
  let state = { messages: [], running: false, pending: false, seen: new Set() };
  state = applyEvent(state, { type: "REPLY_START", reply_id: "r" });
  state = applyEvent(state, {
    type: "TEXT_BLOCK_DELTA",
    reply_id: "r",
    block_id: "b",
    delta: "long",
  });
  state = applyEvent(state, {
    type: "TEXT_BLOCK_END",
    reply_id: "r",
    block_id: "b",
    text: "short",
  });
  state = applyEvent(state, { type: "REQUIRE_USER_CONFIRM", reply_id: "r" });
  assert.equal(state.messages[0].content[0].text, "short");
  assert.equal(state.pending, true);
  assert.equal(state.running, true);
  state = applyEvent(state, {
    type: "REPLY_END",
    reply_id: "r",
    finished_reason: "error",
    error: { message: "fixture failure" },
  });
  assert.equal(state.error, "fixture failure");
  assert.equal(state.pending, false);
});
