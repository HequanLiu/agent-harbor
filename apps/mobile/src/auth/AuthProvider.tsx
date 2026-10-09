import { fetch as expoFetch } from "expo/fetch";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { PropsWithChildren } from "react";
import { HarborClient, ApiError } from "../api/client";
import { API_URL } from "../api/config";
import type { Identity } from "../core/types";
import { loadToken, storeToken } from "./storage";
import { savedLogin } from "./saved-login";
interface AuthState {
  api: HarborClient;
  identity: Identity | null;
  loading: boolean;
  bootError: string;
  retry: () => void;
  login: (email: string, password: string, remember?: boolean) => Promise<void>;
  logout: () => Promise<void>;
  switchTenant: (id: string) => Promise<void>;
}
const Context = createContext<AuthState | null>(null);
export function AuthProvider({ children }: PropsWithChildren) {
  const api = useMemo(
    () => new HarborClient(API_URL, expoFetch as typeof fetch),
    [],
  );
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [loading, setLoading] = useState(true);
  const [bootError, setBootError] = useState("");
  const version = useRef(0);
  const clear = useCallback(async () => {
    version.current++;
    api.setSession("");
    setIdentity(null);
    setBootError("");
    await storeToken(null);
  }, [api]);
  useEffect(() => {
    api.setUnauthorized(() => {
      void clear().catch(() =>
        setBootError("无法清除设备中的登录记录，请重试。"),
      );
    });
    return () => api.setUnauthorized();
  }, [api, clear]);
  const retry = useCallback(async () => {
    const current = ++version.current;
    setLoading(true);
    setBootError("");
    try {
      const token = await loadToken();
      if (current !== version.current) return;
      if (token) {
        api.setSession(token);
        const me = await api.me();
        if (current === version.current) {
          api.setTenant(me.active_tenant_id);
          setIdentity(me);
        }
      }
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401))
        setBootError(
          error instanceof Error ? error.message : "无法恢复登录，请重试。",
        );
    } finally {
      setLoading(false);
    }
  }, [api]);
  // Restore the persisted session on mount; retry also controls the loading screen.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void retry();
  }, [retry]);
  const login = async (email: string, password: string, remember = false) => {
    const result = await api.login(email.trim(), password);
    try {
      await savedLogin.save(
        remember ? { email: email.trim(), password } : null,
      );
      await storeToken(result.access_token);
    } catch {
      const cleanup = new HarborClient(API_URL, expoFetch as typeof fetch);
      cleanup.setSession(result.access_token);
      await cleanup.logout().catch(() => {});
      await storeToken(null).catch(() => {});
      throw new Error("无法保存登录信息，请取消记住密码后重试。");
    }
    version.current++;
    api.setSession(result.access_token, result.identity.active_tenant_id);
    setIdentity(result.identity);
  };
  const logout = async () => {
    try {
      await api.logout();
    } finally {
      await clear();
    }
  };
  const switchTenant = async (id: string) => {
    const me = await api.switchTenant(id);
    api.setTenant(me.active_tenant_id);
    setIdentity(me);
  };
  return (
    <Context.Provider
      value={{
        api,
        identity,
        loading,
        bootError,
        retry: () => {
          void retry();
        },
        login,
        logout,
        switchTenant,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useAuth() {
  const value = useContext(Context);
  if (!value) throw new Error("Missing AuthProvider");
  return value;
}
