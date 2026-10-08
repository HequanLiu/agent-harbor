import { test } from 'node:test';
import assert from 'node:assert/strict';
import { responseBlob, normalizeAbortResponse } from '../src/lib/http-body.ts';
test('native Response exposes MIME through its patched headers', async () => {
 const response = new Response(new Uint8Array([37, 80, 68, 70]));
 Object.defineProperty(response, 'headers', { value: new Headers({ 'Content-Type': 'application/pdf' }) });
 const blob = await responseBlob(response);
 assert.equal(blob.type, 'application/pdf');
 assert.equal(await blob.text(), '%PDF');
});
test('native body cancellation preserves AbortError for upload state', async () => {
 const controller = new AbortController();
 const response = new Response(new ReadableStream({ pull(stream) {
   controller.abort(); stream.error(new Error('Request cancelled'));
 } }));
 await assert.rejects(normalizeAbortResponse(response, controller.signal).text(), { name: 'AbortError' });
});
test('native body timeout preserves TimeoutError', async () => {
 const controller = new AbortController();
 controller.abort(new DOMException('Timed out', 'TimeoutError'));
 await assert.rejects(normalizeAbortResponse(new Response('late'), controller.signal).text(), { name: 'TimeoutError' });
});
test('native body errors remain errors when not cancelled', async () => {
 const controller = new AbortController();
 const response = new Response(new ReadableStream({ start(stream) { stream.error(new Error('Connection lost')); } }));
 await assert.rejects(normalizeAbortResponse(response, controller.signal).text(), /Connection lost/);
});
