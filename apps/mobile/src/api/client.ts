import type {
  Agent,
  ConfirmEvent,
  CredentialChoice,
  History,
  Identity,
  LoginResult,
  Message,
  ModelChoice,
  ModelConfig,
  Session,
} from "../core/types";
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
export class HarborClient {
  base: string;
  token = "";
  tenant = "";
  onUnauthorized?: () => void;
  fetcher: typeof fetch;
  constructor(base: string, fetcher: typeof fetch) {
    this.base = base.replace(/\/+$/, "") + "/";
    this.fetcher = (input, init) => fetcher(input, init);
  }
  setSession(token: string, tenant = "") {
    this.token = token;
    this.tenant = tenant;
  }
  setTenant(tenant: string) {
    this.tenant = tenant;
  }
  setUnauthorized(handler?: () => void) {
    this.onUnauthorized = handler;
  }
  async request<T>(
    path: string,
    options: {
      method?: string;
      body?: unknown;
      signal?: AbortSignal;
      stream?: boolean;
      anonymous?: boolean;
    } = {},
  ): Promise<T> {
    const controller = new AbortController();
    const timer = options.signal
      ? undefined
      : setTimeout(() => controller.abort(), 15000);
    const token = this.token;
    const headers: Record<string, string> = {
      Accept: options.stream ? "text/event-stream" : "application/json",
    };
    if (!options.anonymous && token) headers.Authorization = `Bearer ${token}`;
    if (!options.anonymous && this.tenant) headers["X-Tenant-ID"] = this.tenant;
    if (options.body !== undefined)
      headers["Content-Type"] = "application/json";
    try {
      const response = await this.fetcher(
        new URL(path.replace(/^\/+/, ""), this.base).toString(),
        {
          method: options.method || "GET",
          headers,
          credentials: "omit",
          body:
            options.body === undefined
              ? undefined
              : JSON.stringify(options.body),
          signal: options.signal || controller.signal,
        },
      );
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        if (
          response.status === 401 &&
          !options.anonymous &&
          token === this.token
        )
          this.onUnauthorized?.();
        throw new ApiError(
          response.status,
          typeof body.detail === "string"
            ? body.detail
            : `请求失败（${response.status}）`,
        );
      }
      if (options.stream) return response as T;
      return response.status === 204
        ? (undefined as T)
        : ((await response.json()) as T);
    } catch (error) {
      if (error instanceof ApiError || options.signal?.aborted) throw error;
      throw new ApiError(
        0,
        controller.signal.aborted
          ? "连接超时，请稍后重试。"
          : "无法连接服务，请检查网络和服务地址。",
      );
    } finally {
      clearTimeout(timer);
    }
  }
  login(email: string, password: string) {
    return this.request<LoginResult>("harbor/auth/mobile/login", {
      method: "POST",
      body: { email, password },
      anonymous: true,
    });
  }
  me() {
    return this.request<Identity>("harbor/auth/me");
  }
  logout() {
    return this.request<void>("harbor/auth/logout", { method: "POST" });
  }
  switchTenant(tenant_id: string) {
    return this.request<Identity>("harbor/auth/switch-tenant", {
      method: "POST",
      body: { tenant_id },
    });
  }
  agents() {
    return this.request<{ agents: Agent[] }>("agent/");
  }
  sessions(agent: string) {
    return this.request<{ sessions: Session[] }>(
      `sessions/?agent_id=${encodeURIComponent(agent)}`,
    );
  }
  createSession(agent: string, model: ModelConfig) {
    return this.request<{ session_id: string }>("sessions/", {
      method: "POST",
      body: { agent_id: agent, chat_model_config: model },
    });
  }
  history(
    agent: string,
    session: string,
    before?: string,
    signal?: AbortSignal,
  ) {
    return this.request<History>(
      `sessions/${encodeURIComponent(session)}/messages?agent_id=${encodeURIComponent(agent)}&limit=40${before ? "&before=" + encodeURIComponent(before) : ""}`,
      { signal },
    );
  }
  stream(agent: string, session: string, signal: AbortSignal) {
    return this.request<Response>(
      `sessions/${encodeURIComponent(session)}/stream?agent_id=${encodeURIComponent(agent)}`,
      { signal, stream: true },
    );
  }
  send(agent: string, session: string, input: Message | ConfirmEvent) {
    return this.request("chat/", {
      method: "POST",
      body: { agent_id: agent, session_id: session, input },
    });
  }
  interrupt(agent: string, session: string) {
    return this.request(
      `sessions/${encodeURIComponent(session)}/interrupt?agent_id=${encodeURIComponent(agent)}`,
      { method: "POST" },
    );
  }
  credentials() {
    return this.request<{ credentials: CredentialChoice[] }>(
      "mobile/credentials",
    );
  }
  models(provider: string) {
    return this.request<{ models: ModelChoice[] }>(
      `model/?provider=${encodeURIComponent(provider)}`,
    );
  }
}
