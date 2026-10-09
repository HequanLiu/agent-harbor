import { Anchor, ArrowRight, Eye, EyeOff, Loader2, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { toast } from 'sonner';

import { harborRequest, rememberIdentity } from '@/api/harbor';
import type { Identity } from '@/api/harbor';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { isDesktop } from '@/lib/desktop';
import { clearSavedLogin, loadSavedLogin, saveLogin } from '@/lib/login-credentials';

export function SetupPage({ onComplete }: { onComplete: () => void }) {
  const [register, setRegister] = useState(false);
  const [registrationEnabled, setRegistrationEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberPassword, setRememberPassword] = useState(false);
  const [restoring, setRestoring] = useState(isDesktop);
  useEffect(() => {
    let active = true;
    loadSavedLogin().then(saved => {
      if (active && saved) {
        setEmail(saved.email); setPassword(saved.password); setRememberPassword(true);
      }
    }).catch(() => {
      if (active) setError('无法读取已保存的密码，请手动输入。');
    }).finally(() => { if (active) setRestoring(false); });
    return () => { active = false; };
  }, []);
  async function changeRemember(checked: boolean) {
    if (checked) { setRememberPassword(true); return; }
    setBusy(true); setError('');
    try {
      await clearSavedLogin(); setRememberPassword(false);
    } catch { setError('无法清除已保存的密码，请重试。'); }
    finally { setBusy(false); }
  }

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
      if (isDesktop && !register && rememberPassword) {
        try { await saveLogin({ email, password }); }
        catch { toast.warning('已登录，但密码未能保存，请下次登录时重试。'); }
      }
      setPassword(''); setShowPassword(false);
      rememberIdentity(identity); onComplete();
    } catch (e) { setError(e instanceof Error ? e.message : '登录失败'); }
    finally { setBusy(false); }
  }
  return <main className="min-h-dvh bg-background text-foreground grid lg:grid-cols-2">
    <section className="hidden lg:flex flex-col justify-between p-14 bg-linear-to-r from-teal-50/70 via-slate-50/60 to-background text-slate-900 dark:bg-none dark:bg-slate-950 dark:text-slate-50 relative overflow-hidden">
      <div className="absolute size-[36rem] rounded-full border border-teal-700/8 dark:border-teal-400/15 -right-60 top-20" />
      <div className="absolute size-[26rem] rounded-full border border-teal-700/8 dark:border-teal-400/15 -right-40 top-40" />
      <div className="flex gap-3 items-center text-xl font-semibold"><Anchor className="text-teal-700 dark:text-teal-300" /> AgentHarbor <span className="text-slate-500 dark:text-slate-400 text-sm">智港</span></div>
      <div className="relative max-w-lg lg:ml-6 xl:ml-10"><p className="text-teal-700 dark:text-teal-300 text-xs tracking-[0.24em] mb-7">A HOME FOR YOUR AGENTS</p><h1 className="text-4xl xl:text-5xl font-semibold leading-snug tracking-tight">把任务交给智能体，<br /><span className="text-teal-700 dark:text-teal-300">把时间留给创造。</span></h1><p className="text-slate-500 dark:text-slate-400 mt-7 leading-7">连接知识与工具，让工作更轻松。</p></div>
      <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 lg:ml-6 xl:ml-10"><ShieldCheck size={17} /> 独立空间 · 持续记忆 · 自由扩展</div>
    </section>
    <section className="flex items-center justify-center p-6 sm:p-12"><div className="w-full max-w-sm">
      <div className="flex items-center gap-2 text-xl font-semibold mb-10 lg:hidden"><Anchor /> AgentHarbor · 智港</div>
      <p className="text-sm text-muted-foreground mb-2">欢迎来到智港</p>
      <h2 className="text-3xl font-semibold tracking-tight">{register ? '创建你的工作空间' : '登录工作空间'}</h2>
      <p className="text-sm text-muted-foreground mt-3 mb-8">{register ? '注册账号，开始构建你的第一个 Agent。' : '继续与你的智能体协作。'}</p>
      <form onSubmit={submit} className="space-y-5">
        {register && <label className="block text-sm space-y-2"><span>你的名字</span><Input name="name" required maxLength={80} autoComplete="name" placeholder="如何称呼你" /></label>}
        <label className="block text-sm space-y-2"><span>邮箱</span><Input type="email" name="email" value={email} onChange={e => setEmail(e.target.value)} disabled={busy || restoring} required maxLength={254} autoComplete="username" placeholder="you@company.com" /></label>
        <div className="space-y-2">
          <label htmlFor="login-password" className="text-sm">密码</label>
          <div className="relative">
            <Input id="login-password" className="pr-10" type={showPassword ? 'text' : 'password'} name="password" value={password} onChange={e => setPassword(e.target.value)} disabled={busy || restoring} required minLength={10} maxLength={128} autoComplete={register ? 'new-password' : 'current-password'} placeholder="至少 10 个字符" />
            <button type="button" className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-lg text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={showPassword ? '隐藏密码' : '显示密码'} aria-pressed={showPassword} aria-controls="login-password" onClick={() => setShowPassword(!showPassword)}>
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>
        {!register && isDesktop && <div className="flex items-center gap-2">
          <Checkbox id="remember-password" checked={rememberPassword} disabled={busy || restoring} onCheckedChange={value => { void changeRemember(value === true); }} />
          <label htmlFor="remember-password" className="text-sm cursor-pointer">记住密码</label>
        </div>}
        {register && <label className="block text-sm space-y-2"><span>工作空间名称</span><Input name="tenant_name" required maxLength={80} placeholder="例如：产品团队" /></label>}
        {error && <p role="alert" className="text-sm text-destructive bg-destructive/10 rounded-md p-3">{error}</p>}
        <Button className="w-full h-11" type="submit" disabled={busy || restoring}>{busy || restoring ? <Loader2 className="animate-spin" /> : <>{register ? '创建账号与空间' : '登录'}<ArrowRight size={16} /></>}</Button>
      </form>
      {registrationEnabled && <button type="button" className="text-sm mt-6 text-muted-foreground hover:text-foreground" disabled={busy || restoring} onClick={() => { setRegister(!register); setPassword(''); setShowPassword(false); setError(''); }}>{register ? '已有账号？返回登录' : '第一次使用？创建账号'}</button>}
      <p className="text-xs text-muted-foreground mt-14">AgentHarbor · Built with AgentScope</p>
    </div></section>
  </main>;
}
