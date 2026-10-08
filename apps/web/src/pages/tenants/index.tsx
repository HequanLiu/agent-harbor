import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';

import { harborRequest } from '@/api/harbor';
import type { Member, Tenant } from '@/api/harbor';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useHarbor } from '@/context/HarborContext';
import { navigateApp } from '@/lib/desktop';
export function TenantPage() {
  const identity = useHarbor();
  const tenant = identity.tenants.find(t => t.id === identity.active_tenant_id);
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try { setMembers(await harborRequest<Member[]>(`/tenants/${identity.active_tenant_id}/members`)); }
    catch (e) { setError(e instanceof Error ? e.message : '读取成员失败'); }
  }, [identity.active_tenant_id]);
  useEffect(() => { void refresh(); }, [refresh]);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    const name = new FormData(event.currentTarget).get('name');
    try {
      const created = await harborRequest<Tenant>('/tenants', 'POST', { name });
      await harborRequest('/auth/switch-tenant', 'POST', { tenant_id: created.id });
      navigateApp('/tenants');
    } catch (e) { setError(e instanceof Error ? e.message : '创建失败'); }
    finally { setBusy(false); }
  }
  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    const form = event.currentTarget;
    try {
      await harborRequest(`/tenants/${identity.active_tenant_id}/members`, 'POST', { email: new FormData(form).get('email') });
      form.reset(); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : '添加失败'); }
    finally { setBusy(false); }
  }
  async function remove(member: Member) {
    if (!window.confirm(`移除 ${member.name} 的空间访问权限？`)) return;
    setBusy(true); setError('');
    try { await harborRequest(`/tenants/${identity.active_tenant_id}/members/${member.id}`, 'DELETE'); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : '移除失败'); }
    finally { setBusy(false); }
  }
  return <div className="p-6 sm:p-10 overflow-auto h-full"><div className="max-w-3xl mx-auto space-y-8">
    <div><p className="text-xs tracking-widest text-teal-600 mb-2">WORKSPACE</p><h1 className="text-2xl font-semibold">空间管理</h1><p className="text-muted-foreground text-sm mt-2">在不同团队之间切换，管理成员的访问权限。</p></div>
    {error && <p role="alert" className="p-3 rounded-md bg-destructive/10 text-destructive text-sm">{error}</p>}
    <section className="border rounded-xl p-5 space-y-5"><div><h2 className="font-semibold">{tenant?.name ?? '空间不可用'}</h2><p className="text-sm text-muted-foreground mt-1">{tenant?.role === 'owner' ? '你是这个空间的所有者' : '你是这个空间的成员'}。成员的 Agent、会话和凭据各自独立。</p></div>
      <div className="divide-y">{members.map(member => <div key={member.id} className="flex items-center gap-3 py-3"><div className="size-9 rounded-full bg-muted flex items-center justify-center text-sm">{member.name.slice(0, 1)}</div><div className="min-w-0 flex-1"><p className="text-sm font-medium truncate">{member.name}</p><p className="text-xs text-muted-foreground truncate">{member.email}</p></div><span className="text-xs text-muted-foreground">{member.role === 'owner' ? '所有者' : '成员'}</span>{tenant?.role === 'owner' && member.role !== 'owner' && <Button size="sm" variant="ghost" disabled={busy} onClick={() => void remove(member)}>移除</Button>}</div>)}</div>
      {tenant?.role === 'owner' && <form onSubmit={add} className="space-y-2"><label htmlFor="member-email" className="text-sm font-medium">添加已注册成员</label><div className="flex gap-2"><Input id="member-email" type="email" name="email" required placeholder="成员邮箱" /><Button disabled={busy}>添加</Button></div><p className="text-xs text-muted-foreground">请对方先在此服务注册账号。</p></form>}
    </section>
    <section className="border rounded-xl p-5"><h2 className="font-semibold mb-4">创建新的工作空间</h2><form onSubmit={create} className="flex gap-2"><Input aria-label="新空间名称" name="name" required maxLength={80} placeholder="例如：研发团队" /><Button disabled={busy}>创建空间</Button></form></section>
  </div></div>;
}
