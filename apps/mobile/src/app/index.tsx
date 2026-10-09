import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Text, View } from "react-native";
import { router } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { useAuth } from "../auth/AuthProvider";
import { defaultChat } from "../core/default-chat";
import type { DefaultChat } from "../core/default-chat";
import { Action, colors, Notice, styles } from "../components/ui";
export default function Home() {
  const { api, identity } = useAuth();
  const tenant = identity?.active_tenant_id;
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const task = useRef<{key: string; promise: Promise<DefaultChat>} | null>(null);
  useEffect(() => {
    let active = true;
    const token = api.token;
    const key = `${tenant}:${attempt}`;
    // Reuse initialization during effect replay so a first visit creates once.
    if (task.current?.key !== key) task.current = {key, promise: defaultChat(api, () => api.tenant === tenant && api.token === token)};
    task.current.promise.then(params => { if (active) router.replace({pathname: "/chat/[id]", params: {...params}}); })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : "无法加载默认对话"); });
    return () => { active = false; };
  }, [api, tenant, attempt]);
  return <SafeAreaView style={styles.screen}><View style={[styles.frame, {justifyContent: "center", padding: 28, gap: 20}]}>
    {error ? <><Notice text={error} /><Action title="重试" onPress={() => {setError(""); setAttempt(x => x + 1);}} /><Action title="会话与模型设置" secondary onPress={() => router.replace("/history")} /></> : <><ActivityIndicator color={colors.teal} /><Text style={[styles.muted, {textAlign: "center"}]}>正在准备你的对话…</Text></>}
  </View></SafeAreaView>;
}
