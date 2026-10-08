import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeServerUrl, routeHref } from '../src/lib/desktop-config.ts';
test('server URL preserves reverse proxy prefix', () => {
 assert.equal(normalizeServerUrl(' https://example.com/harbor '), 'https://example.com/harbor/');
 assert.equal(normalizeServerUrl('http://127.0.0.1:8017'), 'http://127.0.0.1:8017/');
});
test('reject insecure remote hosts and ambiguous credentials', () => {
 for (const value of ['http://example.com', 'https://user:secret@example.com', 'https://example.com/?a=1', 'https://example.com/#x', 'file:///tmp', 'garbage']) assert.throws(() => normalizeServerUrl(value));
});
test('desktop routes stay on asset origin', () => {
 assert.equal(routeHref('/chat', true), '/#/chat');
 assert.equal(routeHref('/tenants', false), '/tenants');
});
