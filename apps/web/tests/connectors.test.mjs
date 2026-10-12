import assert from 'node:assert/strict';
import test from 'node:test';
import { validateConnectorArchive, connectorAuthorizationUrl } from '../src/lib/connector-validation.ts';

test('archive validation bounds the upload before reading bytes', () => {
  assert.equal(validateConnectorArchive({ name: 'WorkBuddy.ZIP', size: 5 * 1024 * 1024 }), null);
  assert.match(validateConnectorArchive({ name: 'x.zip', size: 5 * 1024 * 1024 + 1 }), /5 MiB/);
  assert.ok(validateConnectorArchive({ name: 'x.zip', size: 0 }));
  assert.ok(validateConnectorArchive({ name: 'x.exe', size: 1 }));
});

test('authorization accepts HTTPS and loopback HTTP only', () => {
  assert.equal(connectorAuthorizationUrl('https://mes.example/oauth'), 'https://mes.example/oauth');
  assert.equal(connectorAuthorizationUrl('http://localhost:8000/oauth'), 'http://localhost:8000/oauth');
  for (const url of ['javascript:alert(1)', 'data:text/html,hi', 'http://mes.example/oauth', 'https://user:pass@mes.example/oauth', '/oauth']) {
    assert.throws(() => connectorAuthorizationUrl(url));
  }
});

import * as validation from '../src/lib/connector-validation.ts';

test('desktop authorization opens system browser without creating a popup', async () => {
  assert.equal(typeof validation.authorizeConnector, 'function');
  const calls = [];
  await validation.authorizeConnector({
    desktop: true,
    request: async external => { calls.push(['request', external]); return { authorization_url: 'https://harbor.example/harbor/connectors/oauth/browser#ticket' }; },
    openPopup: () => { throw new Error('Desktop must not use window.open'); },
    openExternal: async url => { calls.push(['external', url]); },
  });
  assert.deepEqual(calls, [['request', true], ['external', 'https://harbor.example/harbor/connectors/oauth/browser#ticket']]);
});

test('web authorization reserves popup before requesting authorization', async () => {
  assert.equal(typeof validation.authorizeConnector, 'function');
  const calls = [];
  const popup = { opener: {}, location: { href: '' }, close() { calls.push('close'); } };
  await validation.authorizeConnector({
    desktop: false,
    openPopup: () => { calls.push('popup'); return popup; },
    request: async external => { calls.push(external); return { authorization_url: 'https://mes.example/oauth' }; },
    openExternal: async () => { throw new Error('Must keep browser popup flow'); },
  });
  assert.deepEqual(calls, ['popup', false]);
  assert.equal(popup.opener, null);
  assert.equal(popup.location.href, 'https://mes.example/oauth');
});

test('authorization rejects unsafe URLs and propagates external opener failures', async () => {
  assert.equal(typeof validation.authorizeConnector, 'function');
  let opened = false;
  await assert.rejects(validation.authorizeConnector({
    desktop: true, request: async () => ({ authorization_url: 'file:///secret' }),
    openPopup: () => null, openExternal: async () => { opened = true; },
  }));
  assert.equal(opened, false);
  await assert.rejects(validation.authorizeConnector({
    desktop: true, request: async () => ({ authorization_url: 'https://harbor.example/oauth' }),
    openPopup: () => null, openExternal: async () => { throw new Error('opener failed'); },
  }), /opener failed/);
});

test('authorization closes reserved popup when request fails', async () => {
  assert.equal(typeof validation.authorizeConnector, 'function');
  let closed = false;
  await assert.rejects(validation.authorizeConnector({
    desktop: false,
    request: async () => { throw new Error('offline'); },
    openPopup: () => ({ opener: null, location: { href: '' }, close() { closed = true; } }),
    openExternal: async () => {},
  }), /offline/);
  assert.equal(closed, true);
});
