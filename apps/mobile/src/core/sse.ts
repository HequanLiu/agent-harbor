import type { AgentEvent } from "./types";
/** JSON frames and UTF-8 characters may span network chunks. */
export async function* readEvents(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<AgentEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let data: string[] = [];
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += done
        ? decoder.decode()
        : decoder.decode(value, { stream: true });
      let match: RegExpExecArray | null;
      while ((match = /\r\n|\n|\r/.exec(buffer))) {
        if (!done && match[0] === "\r" && match.index === buffer.length - 1)
          break;
        const line = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        if (line === "") {
          if (data.length) {
            const payload = data.join("\n");
            data = [];
            if (payload !== "[DONE]") yield JSON.parse(payload) as AgentEvent;
          }
        } else if (line.startsWith("data:"))
          data.push(line.slice(5).replace(/^ /, ""));
      }
      if (done) break;
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
