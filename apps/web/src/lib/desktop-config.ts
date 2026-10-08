export function normalizeServerUrl(value: string): string {
  const url = new URL(value.trim());
  const local = ['localhost', '127.0.0.1'].includes(url.hostname);
  if ((url.protocol !== 'https:' && !(url.protocol === 'http:' && local)) ||
      url.username || url.password || url.search || url.hash) {
    throw new Error('远程服务请使用 HTTPS；本机可使用 HTTP。地址不能包含账号、参数或片段。');
  }
  url.pathname = url.pathname.replace(/\/+$/, '') + '/';
  return url.toString();
}

export const routeHref = (path: string, desktop: boolean) => desktop ? `/#${path}` : path;
