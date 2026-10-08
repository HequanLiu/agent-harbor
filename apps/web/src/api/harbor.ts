import { apiBaseUrl, apiFetch } from '@/lib/desktop';

export interface Tenant { id: string; name: string; role: 'owner' | 'member' }
export interface Identity {
  user: { id: string; name: string; email: string };
  active_tenant_id: string;
  tenants: Tenant[];
}
export interface Member { id: string; name: string; email: string; role: 'owner' | 'member' }
export async function harborRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await apiFetch(new URL(`harbor${path}`, apiBaseUrl()), {
    method, credentials: 'same-origin',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '服务连接失败，请检查后端是否已启动' }));
    throw new Error(typeof error.detail === 'string' ? error.detail : '输入格式不正确，请检查后重试');
  }
  return response.status === 204 ? undefined as T : response.json();
}
export function rememberIdentity(identity: Identity) {
  sessionStorage.setItem('harbor_tenant', identity.active_tenant_id);
  sessionStorage.setItem('harbor_user', `${identity.active_tenant_id}_${identity.user.id}`);
}
