export function validateConnectorArchive(file: { name: string; size: number }): string | null {
  if (!/\.zip$/i.test(file.name)) return '请选择 ZIP 连接器包';
  if (file.size === 0) return '连接器包不能为空';
  if (file.size > 5 * 1024 * 1024) return '连接器包不能超过 5 MiB';
  return null;
}

export function connectorAuthorizationUrl(value: string): string {
  const url = new URL(value);
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if (url.username || url.password || (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback))) {
    throw new Error('连接器返回了不安全的授权地址');
  }
  return url.href;
}

type AuthorizationPopup = {
  opener: unknown;
  location: { href: string };
  close(): void;
};

export async function authorizeConnector(options: {
  desktop: boolean;
  request(externalBrowser: boolean): Promise<{ authorization_url: string }>;
  openPopup(): AuthorizationPopup | null;
  openExternal(url: string): Promise<void>;
}): Promise<void> {
  // Reserve the web popup synchronously while the click is still active.
  const popup = options.desktop ? null : options.openPopup();
  if (!options.desktop && !popup) throw new Error('浏览器阻止了授权窗口，请允许弹出窗口后重试');
  try {
    if (popup) popup.opener = null;
    const result = await options.request(options.desktop);
    const url = connectorAuthorizationUrl(result.authorization_url);
    if (options.desktop) await options.openExternal(url);
    else if (popup) popup.location.href = url;
  } catch (error) {
    popup?.close();
    throw error;
  }
}
