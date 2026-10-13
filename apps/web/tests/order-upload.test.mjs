import assert from 'node:assert/strict';
import test from 'node:test';
import { mergeUploadedPayload, sourceUploadError } from '../src/lib/order-upload.ts';

test('attaching a picture preserves unsaved fields and uses the new server sources', () => {
  const local = { style: { picture_asset_id: null, style_num: 'NEW', colors: [{ name: '蓝' }] }, order: { due_date: '2026-11-01' }, pos: [{ po_num: 'PO-2' }], sources: [] };
  const server = { ...local, style: { style_num: 'OLD' }, sources: [{ asset_id: 'image-1' }] };
  const result = mergeUploadedPayload(server, local, { path: ['style', 'picture_asset_id'], assetId: 'image-1' });
  assert.equal(result.style.picture_asset_id, 'image-1');
  assert.equal(result.style.style_num, 'NEW');
  assert.deepEqual(result.order, local.order);
  assert.deepEqual(result.pos, local.pos);
  assert.deepEqual(result.sources, server.sources);
  assert.equal(local.style.picture_asset_id, null);
  assert.equal(server.style.style_num, 'OLD');
});

test('source-only uploads keep existing picture and unsaved evidence decisions', () => {
  const local = { style: { picture_asset_id: 'existing' }, evidence: [{ needs_review: true }] };
  const server = { sources: [{ asset_id: 'doc-1' }], evidence: [{ needs_review: false }] };
  const result = mergeUploadedPayload(server, local);
  assert.equal(result.style.picture_asset_id, 'existing');
  assert.deepEqual(result.evidence, server.evidence);
});

test('upload error exposes actionable upstream message and status', () => {
  assert.match(sourceUploadError({ error: { code: 'UPLOAD_DISABLED', message: 'MES 图片上传未配置' } }, 422), /MES 图片上传未配置/);
  assert.match(sourceUploadError({ detail: '文件过大' }, 413), /文件过大/);
  assert.match(sourceUploadError({}, 502), /502/);
});
