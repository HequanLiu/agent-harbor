import { Anchor, ArrowRight, Loader2, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';

import { harborRequest, rememberIdentity } from '@/api/harbor';
import type { Identity } from '@/api/harbor';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { isDesktop, getServerUrl, setServerUrl } from '@/lib/desktop';

export function SetupPage({ onComplete }: { onComplete: () => void }) {
  const [server, setServer] = useState(getServerUrl);
  const [register, setRegister] = useState(false);
  const [registrationEnabled, setRegistrationEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    harborRequest<{ registration_enabled: boolean }>('/auth/status')
      .then(r => setRegistrationEnabled(r.registration_enabled))
      .catch(() => setError('无法连接后端，请确认 AgentHarbor 服务已启动。'));
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    const form = new FormData(event.currentTarget);
    try {
      const identity = await harborRequest<Identity>(register ? '/auth/register' : '/auth/login', 'POST', Object.fromEntries(form));
      rememberIdentity(identity); onComplete();
    } catch (e) { setError(e instanceof Error ? e.message : '登录失败'); }
    finally { setBusy(false); }
  }
  return <main className="min-h-dvh bg-background text-foreground grid lg:grid-cols-2">
    <section className="hidden lg:flex flex-col justify-between p-14 bg-slate-950 text-slate-50 relative overflow-hidden">
      <div className="absolute size-[36rem] rounded-full border border-teal-400/15 -right-60 top-20" />
      <div className="absolute size-[26rem] rounded-full border border-teal-400/15 -right-40 top-40" />
      <div className="flex gap-3 items-center text-xl font-semibold"><Anchor className="text-teal-300" /> AgentHarbor <span className="text-slate-400 text-sm">智港</span></div>
      <div className="relative max-w-lg"><p className="text-teal-300 text-xs tracking-[0.24em] mb-7">A HOME FOR YOUR AGENTS</p><h1 className="text-5xl font-semibold leading-snug tracking-tight">让每个团队，<br />拥有自己的<br /><span className="text-teal-300">智能体空间。</span></h1><p className="text-slate-400 mt-7 leading-7">连接模型、工具与知识。<br />从一次对话开始，让智能体走进日常工作。</p></div>
      <div className="flex items-center gap-2 text-sm text-slate-400"><ShieldCheck size={17} /> 独立空间 · 持续记忆 · 自由扩展</div>
    </section>
    <section className="flex items-center justify-center p-6 sm:p-12"><div className="w-full max-w-sm">
      <div className="flex items-center gap-2 text-xl font-semibold mb-10 lg:hidden"><Anchor /> AgentHarbor · 智港</div>
      <p className="text-sm text-muted-foreground mb-2">欢迎来到智港</p>
      <h2 className="text-3xl font-semibold tracking-tight">{register ? '创建你的工作空间' : '登录工作空间'}</h2>
      <p className="text-sm text-muted-foreground mt-3 mb-8">{register ? '注册账号，开始构建你的第一个 Agent。' : '继续与你的智能体协作。'}</p>
      {isDesktop && <div className="mb-6 space-y-2">
        <label htmlFor="server-url" className="text-sm">后端服务地址</label>
        <div className="flex gap-2"><Input id="server-url" value={server} onChange={e => setServer(e.target.value)} placeholder="http://127.0.0.1:8017" />
          <Button type="button" variant="outline" onClick={() => { try { setServerUrl(server); window.location.reload(); } catch (e) { setError((e as Error).message); } }}>连接</Button></div>
        <p className="text-xs text-muted-foreground">本机使用 HTTP，远程服务器使用 HTTPS。更改后点击连接。</p>
      </div>}
      <form onSubmit={submit} className="space-y-5">
        {register && <label className="block text-sm space-y-2"><span>你的名字</span><Input name="name" required maxLength={80} autoComplete="name" placeholder="如何称呼你" /></label>}
        <label className="block text-sm space-y-2"><span>邮箱</span><Input type="email" name="email" required maxLength={254} autoComplete="email" placeholder="you@company.com" /></label>
        <label className="block text-sm space-y-2"><span>密码</span><Input type="password" name="password" required minLength={10} maxLength={128} autoComplete={register ? 'new-password' : 'current-password'} placeholder="至少 10 个字符" /></label>
        {register && <label className="block text-sm space-y-2"><span>工作空间名称</span><Input name="tenant_name" required maxLength={80} placeholder="例如：产品团队" /></label>}
        {error && <p role="alert" className="text-sm text-destructive bg-destructive/10 rounded-md p-3">{error}</p>}
        <Button className="w-full h-11" type="submit" disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <>{register ? '创建账号与空间' : '登录'}<ArrowRight size={16} /></>}</Button>
      </form>
      {registrationEnabled && <button type="button" className="text-sm mt-6 text-muted-foreground hover:text-foreground" onClick={() => { setRegister(!register); setError(''); }}>{register ? '已有账号？返回登录' : '第一次使用？创建账号'}</button>}
      <p className="text-xs text-muted-foreground mt-14">AgentHarbor · Built with AgentScope</p>
    </div></section>
  </main>;
}
