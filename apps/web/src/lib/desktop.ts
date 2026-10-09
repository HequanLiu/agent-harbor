import { isTauri } from '@tauri-apps/api/core';

import { normalizeServerUrl, routeHref } from './desktop-config';
import { responseBlob, abortReason, normalizeAbortResponse } from './http-body';

export const isDesktop = isTauri();
export const getServerUrl = () => import.meta.env.VITE_HARBOR_SERVER_URL || 'http://127.0.0.1:8017/';
export const apiBaseUrl = () => isDesktop ? normalizeServerUrl(getServerUrl()) : `${window.location.origin}/api/`;
export const appHref = (path: string) => routeHref(path, isDesktop);
export function navigateApp(path: string) {
  window.location.assign(appHref(path));
  if (isDesktop) window.location.reload();
}

export async function apiFetch(input: string | URL, init?: RequestInit): Promise<Response> {
  if (isDesktop) {
    const { fetch } = await import('@tauri-apps/plugin-http');
    try {
      const response = await fetch(input, init);
      return normalizeAbortResponse(response, init?.signal ?? undefined);
    } catch (error) {
      if (init?.signal?.aborted) throw abortReason(init.signal);
      throw error;
    }
  }
  return window.fetch(input, init);
}

export async function nativeUpload(url: URL, body: FormData, signal?: AbortSignal): Promise<Response> {
  const response = await apiFetch(url, { method: 'POST', body, signal,
    headers: { 'X-Tenant-ID': sessionStorage.getItem('harbor_tenant') ?? '' } });
  if (response.status === 401) window.dispatchEvent(new Event('harbor:unauthorized'));
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof error.detail === 'string' ? error.detail : '上传失败');
  }
  return response;
}

export async function authenticatedBlob(url: string): Promise<Blob> {
  const response = await apiFetch(url, { headers: { 'X-Tenant-ID': sessionStorage.getItem('harbor_tenant') ?? '' } });
  if (!response.ok) throw new Error(`下载失败 (${response.status})`);
  return responseBlob(response);
}

export async function saveDocument(url: string, filename: string) {
  if (!isDesktop) { window.open(url, '_blank', 'noopener'); return; }
  const { save } = await import('@tauri-apps/plugin-dialog');
  const path = await save({ defaultPath: filename.replace(/[\\/:*?"<>|]/g, '_') });
  if (!path) return;
  const blob = await authenticatedBlob(url);
  const { writeFile } = await import('@tauri-apps/plugin-fs');
  await writeFile(path, new Uint8Array(await blob.arrayBuffer()));
}
