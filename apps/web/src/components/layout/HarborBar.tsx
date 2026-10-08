import { Anchor, LogOut, Users } from 'lucide-react';
import { toast } from 'sonner';

import { harborRequest } from '@/api/harbor';
import { useHarbor } from '@/context/HarborContext';
import { appHref, navigateApp } from '@/lib/desktop';
import { queryClient } from '@/lib/query-client';
export function HarborBar() {
  const identity = useHarbor();
  async function switchTenant(tenantId: string) {
    try {
      await harborRequest('/auth/switch-tenant', 'POST', { tenant_id: tenantId });
      queryClient.clear(); navigateApp('/chat');
    } catch (e) { toast.error(e instanceof Error ? e.message : '切换失败'); }
  }
  async function logout() {
    try {
      await harborRequest('/auth/logout', 'POST');
      sessionStorage.removeItem('harbor_tenant'); sessionStorage.removeItem('harbor_user');
      queryClient.clear(); navigateApp('/');
    } catch (e) { toast.error(e instanceof Error ? e.message : '退出失败'); }
  }
  return <header className="h-14 shrink-0 flex items-center gap-3 px-4 border-b bg-background">
    <a href={appHref('/chat')} className="flex items-center gap-2 font-semibold text-sm"><Anchor className="text-teal-600" size={19} /><span className="hidden sm:inline">AgentHarbor</span></a>
    <span className="text-border">/</span>
    <select aria-label="切换工作空间" value={identity.active_tenant_id} onChange={e => void switchTenant(e.target.value)} className="text-sm bg-background rounded-md border px-2 py-1.5 max-w-48">
      {!identity.tenants.some(t => t.id === identity.active_tenant_id) && <option value={identity.active_tenant_id}>请选择空间</option>}
      {identity.tenants.map(tenant => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}
    </select>
    <a href={appHref('/tenants')} className="text-xs flex gap-1 items-center text-muted-foreground hover:text-foreground"><Users size={15} /><span className="hidden sm:inline">空间管理</span></a>
    <span className="ml-auto text-xs text-muted-foreground truncate">{identity.user.name}</span>
    <button aria-label="退出登录" title="退出登录" onClick={() => void logout()} className="p-2 hover:bg-muted rounded-md"><LogOut size={16} /></button>
  </header>;
}
