/** Native HTTP exposes headers after Response construction; preserve MIME on Blob URLs. */
export async function responseBlob(response: Response): Promise<Blob> {
  const blob = await response.blob();
  const type = response.headers.get('content-type') || blob.type || 'application/octet-stream';
  return blob.type === type ? blob : new Blob([blob], { type });
}

export function abortReason(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException('Aborted', 'AbortError');
}

/** Keep the browser AbortSignal contract while consuming a native response body. */
export function normalizeAbortResponse(response: Response, signal?: AbortSignal): Response {
  if (!signal || !response.body) return response;
  const reader = response.body.getReader();
  const body = new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        if (signal.aborted) throw abortReason(signal);
        const { value, done } = await reader.read();
        if (signal.aborted) throw abortReason(signal);
        if (done) controller.close(); else controller.enqueue(value);
      } catch (error) {
        controller.error(signal.aborted ? abortReason(signal) : error);
        void reader.cancel().catch(() => {});
      }
    },
    cancel: (reason) => reader.cancel(reason),
  });
  return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
}
