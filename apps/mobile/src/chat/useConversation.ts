import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";
import { useAuth } from "../auth/AuthProvider";
import { ApiError } from "../api/client";
import { applyEvent, hasPendingTool, reconcileHistory, getConfirmations, confirmationKey } from "../core/messages";
import type { ChatState } from "../core/messages";
import type { Message, Confirmation, PermissionRule } from "../core/types";
import { readEvents } from "../core/sse";
const empty = (): ChatState => ({
  messages: [],
  running: false,
  pending: false,
  seen: new Set(),
});
export function useConversation(agent: string, session: string) {
  const { api, identity } = useAuth();
  const tenant = identity?.active_tenant_id;
  const [state, setState] = useState<ChatState>(empty);
  const stateRef = useRef(state);
  const [connected, setConnected] = useState(false);
  const connectedRef = useRef(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmationError, setConfirmationError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [olderBusy, setOlderBusy] = useState(false);
  const [interrupting, setInterrupting] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [active, setActive] = useState(true);
  const generation = useRef(0);
  const sendLock = useRef(false);
  const confirmLocks = useRef(new Set<string>());
  const [confirming, setConfirming] = useState<string[]>([]);
  const publish = useCallback((next: ChatState) => {
    stateRef.current = next;
    setState(next);
  }, []);
  const reconnect = useCallback(() => setAttempt((x) => x + 1), []);
  useEffect(() => {
    const subscription = AppState.addEventListener("change", (value) =>
      setActive(value === "active"),
    );
    return () => subscription.remove();
  }, []);
  useEffect(() => {
    const version = ++generation.current;
    const controller = new AbortController();
    let disposed = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    let reconcileTimer: ReturnType<typeof setInterval> | undefined;
    let reconciling = false;
    let needsReconcile = true;
    const reconcile = async () => {
      if (disposed || reconciling || sendLock.current || (!needsReconcile && !stateRef.current.running)) return;
      reconciling = true;
      const snapshot = stateRef.current;
      try {
        const history = await api.history(agent, session, undefined, controller.signal);
        // A newer event or send wins over an older HTTP snapshot. A completed
        // reply is persisted after REPLY_END, so keep checking until unlocked.
        if (disposed || snapshot !== stateRef.current || sendLock.current || history.is_running) return;
        publish(reconcileHistory(snapshot, history));
        setHasMore(history.has_more);
        setInterrupting(false);
        needsReconcile = false;
      } catch {
        // The SSE path owns connectivity errors; 401 still clears authentication.
      } finally {
        reconciling = false;
      }
    };
    // Clear stale network state when the subscription or resource changes.
    connectedRef.current = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setConnected(false);
    setLoading(true);
    setError("");
    setInterrupting(false);
    sendLock.current = false;
    confirmLocks.current.clear();
    setConfirming([]);
    if (!active) {
      setLoading(false);
      return () => {
        disposed = true;
      };
    }
    const connect = async () => {
      try {
        timeout = setTimeout(() => controller.abort(), 20000);
        const history = await api.history(
          agent,
          session,
          undefined,
          controller.signal,
        );
        if (disposed) return;
        const pending = hasPendingTool(history.messages);
        publish({
          messages: history.messages,
          running: history.is_running || pending,
          pending,
          seen: new Set(),
        });
        setHasMore(history.has_more);
        setLoading(false);
        const response = await api.stream(agent, session, controller.signal);
        clearTimeout(timeout);
        if (disposed) return;
        if (!response.body) throw new Error("当前网络不支持流式回复。");
        connectedRef.current = true;
        setConnected(true);
        setError("");
        // Close the history/subscription gap and recover trimmed replay frames.
        reconcileTimer = setInterval(() => { void reconcile(); }, 3000);
        void reconcile();
        for await (const event of readEvents(response.body)) {
          if (disposed) break;
          const next = applyEvent(stateRef.current, event);
          publish(next);
          if (event.type === "REPLY_END") {
            setInterrupting(false);
            needsReconcile = true;
            void reconcile();
          }
        }
        if (!disposed) throw new Error("连接已断开，正在重新连接…");
      } catch (e) {
        if (disposed || version !== generation.current) return;
        connectedRef.current = false;
        setConnected(false);
        setLoading(false);
        if (e instanceof ApiError && e.status === 401) return;
        setError(
          controller.signal.aborted
            ? "连接超时，正在重新连接…"
            : e instanceof Error
              ? e.message
              : "连接已断开",
        );
        retryTimer = setTimeout(reconnect, 3000);
      } finally {
        clearInterval(reconcileTimer);
        clearTimeout(timeout);
      }
    };
    void connect();
    return () => {
      disposed = true;
      controller.abort();
      clearInterval(reconcileTimer);
      clearTimeout(timeout);
      clearTimeout(retryTimer);
      connectedRef.current = false;
    };
  }, [api, agent, session, tenant, attempt, active, publish, reconnect]);
  useEffect(() => {
    if (!interrupting) return;
    const timer = setTimeout(reconnect, 10000);
    return () => clearTimeout(timer);
  }, [interrupting, reconnect]);
  const send = async (text: string) => {
    if (
      !text.trim() ||
      sendLock.current ||
      stateRef.current.running ||
      !connectedRef.current
    )
      return false;
    sendLock.current = true;
    setError("");
    const version = generation.current;
    const message: Message = {
      id: `mobile-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      role: "user",
      name: "user",
      content: [{ type: "text", text: text.trim() }],
    };
    publish({
      ...stateRef.current,
      messages: [...stateRef.current.messages, message],
      running: true,
      error: undefined,
    });
    try {
      await api.send(agent, session, message);
      return true;
    } catch (e) {
      if (version === generation.current) {
        setError(e instanceof Error ? e.message : "发送失败");
        reconnect();
      }
      throw e;
    } finally {
      sendLock.current = false;
    }
  };
  const confirm = async (entry: Confirmation, approved: boolean, rules?: PermissionRule[]) => {
    const key = confirmationKey(entry);
    if (!connectedRef.current || confirmLocks.current.has(key) || !getConfirmations(stateRef.current).some((c) => confirmationKey(c) === key)) return;
    confirmLocks.current.add(key);
    setConfirming([...confirmLocks.current]);
    setConfirmationError("");
    setError("");
    const version = generation.current;
    try {
      await api.send(agent, session, {
        type: "USER_CONFIRM_RESULT",
        id: `mobile-confirm-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        created_at: new Date().toISOString(),
        reply_id: entry.replyId,
        confirm_results: [{ confirmed: approved, tool_call: entry.toolCall, rules: approved ? rules ?? null : null }],
      });
      // Keep the card disabled until SSE or authoritative history settles it.
    } catch (e) {
      if (version === generation.current) {
        setConfirmationError(`${e instanceof Error ? e.message : "确认提交失败"} 已重新同步，请核对操作状态后重试。`);
        reconnect();
      }
    }
  };
  const stop = async () => {
    if (interrupting) return;
    setInterrupting(true);
    try {
      await api.interrupt(agent, session);
    } catch (e) {
      setInterrupting(false);
      setError(e instanceof Error ? e.message : "停止失败，请重试");
    }
  };
  const older = async () => {
    if (olderBusy || !hasMore || !stateRef.current.messages[0]) return;
    setOlderBusy(true);
    const version = generation.current;
    try {
      const history = await api.history(
        agent,
        session,
        stateRef.current.messages[0].id,
      );
      if (version !== generation.current) return;
      const ids = new Set(stateRef.current.messages.map((m) => m.id));
      publish({
        ...stateRef.current,
        messages: [
          ...history.messages.filter((m) => !ids.has(m.id)),
          ...stateRef.current.messages,
        ],
      });
      setHasMore(history.has_more);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setOlderBusy(false);
    }
  };
  return {
    ...state,
    connected,
    loading,
    error: confirmationError || error || state.error,
    hasMore,
    olderBusy,
    interrupting,
    confirmations: getConfirmations(state),
    confirming,
    confirm,
    send,
    stop,
    older,
    reconnect,
  };
}
