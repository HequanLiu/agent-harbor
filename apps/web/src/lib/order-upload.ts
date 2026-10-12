export type PicturePath = (string | number)[];
const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};

export function mergeUploadedPayload(
  server: Record<string, unknown>, local: Record<string, unknown>,
  picture?: { path: PicturePath; assetId: string },
): Record<string, unknown> {
  const result = { ...server };
  for (const key of ['order', 'style', 'pos', 'bom', 'expected_total']) {
    if (Object.hasOwn(local, key)) result[key] = local[key];
  }
  if (!picture) return result;
  function assign(value: unknown, path: PicturePath): unknown {
    if (!path.length) return picture!.assetId;
    const [key, ...rest] = path;
    if (['__proto__', 'constructor', 'prototype'].includes(String(key))) throw new Error('无效的图片字段');
    if (Array.isArray(value) && typeof key === 'number') {
      const copy = [...value]; copy[key] = assign(copy[key], rest); return copy;
    }
    const copy = { ...record(value) }; copy[key] = assign(copy[key], rest); return copy;
  }
  return assign(result, picture.path) as Record<string, unknown>;
}

export function sourceUploadError(body: unknown, status: number): string {
  const data = record(body), error = record(data.error);
  const message = typeof error.message === 'string' ? error.message : typeof data.detail === 'string' ? data.detail : '请检查文件格式、大小与 MES 图片上传配置';
  return `上传失败（${status}）：${message}`;
}
