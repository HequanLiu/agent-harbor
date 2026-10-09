import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Modal,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "../auth/AuthProvider";
import type { Agent, Session } from "../core/types";
import { Action, colors, IconButton, Notice, styles } from "../components/ui";
import { BrandLogo } from "../components/BrandLogo";
import { defaultChat } from "../core/default-chat";
export default function History() {
  const { api, identity, logout, switchTenant } = useAuth();
  const tenant = identity?.active_tenant_id;
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selected, setSelected] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const createLock = useRef(false);
  const [account, setAccount] = useState(false);
  const [accountBusy, setAccountBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const generation = useRef(0);
  // Clear stale network state when the subscription or resource changes.
  useEffect(() => {
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAgents([]);
    setSessions([]);
    setSelected("");
    setLoading(true);
    setError("");
    api
      .agents()
      .then((result) => {
        if (active) {
          setAgents(result.agents);
          setSelected(result.agents[0]?.id || "");
          if (!result.agents.length) setLoading(false);
        }
      })
      .catch((e) => {
        if (active) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [api, tenant, refresh]);
  useFocusEffect(
    useCallback(() => {
      if (!selected || !tenant) return;
      const version = ++generation.current;
      setLoading(true);
      setError("");
      setSessions([]);
      api
        .sessions(selected)
        .then((result) => {
          if (version === generation.current)
            setSessions(
              result.sessions.sort((a, b) =>
                b.session.updated_at.localeCompare(a.session.updated_at),
              ),
            );
        })
        .catch((e) => {
          if (version === generation.current) setError(e.message);
        })
        .finally(() => {
          if (version === generation.current) setLoading(false);
        });
      return () => {
        generation.current++;
      };
    }, [api, selected, tenant]),
  );
  const agentName =
    agents.find((a) => a.id === selected)?.data.name || "智能体";
  const openChat = (id: string, name: string) =>
    router.push({
      pathname: "/chat/[id]",
      params: { id, agentId: selected, name, agentName, model: sessions.find(s => s.session.id === id)?.session.config.chat_model_config?.model },
    });
  const create = async () => {
    if (createLock.current || !selected) return;
    createLock.current = true;
    setCreating(true);
    setError("");
    const version = generation.current;
    const token = api.token;
    const current = () => version === generation.current && api.tenant === tenant && api.token === token;
    try {
      const next = await defaultChat(api, current, { agentId: selected, createNew: true });
      if (current()) router.push({ pathname: "/chat/[id]", params: { ...next } });
    } catch (e) {
      if (current()) setError(e instanceof Error ? e.message : "创建对话失败，请重试");
    } finally {
      createLock.current = false;
      setCreating(false);
    }
  };
  const changeTenant = async (id: string) => {
    setAccountBusy(true);
    setError("");
    try {
      await switchTenant(id);
      setAccount(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "切换失败");
    } finally {
      setAccountBusy(false);
    }
  };
  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.frame}>
        <View
          style={[
            styles.row,
            {
              paddingHorizontal: 24,
              paddingTop: 12,
              paddingBottom: 20,
              justifyContent: "space-between",
            },
          ]}
        >
          <View style={styles.row}>
            <BrandLogo size={38} />
            <View>
              <Text
                style={{ fontSize: 19, fontWeight: "700", color: colors.ink }}
              >
                智港
              </Text>
              <Text
                numberOfLines={1}
                style={[styles.muted, { maxWidth: 230, fontSize: 11 }]}
              >
                {identity?.tenants.find((t) => t.id === tenant)?.name}
              </Text>
            </View>
          </View>
          <IconButton
            icon="person-circle-outline"
            label="账户与工作空间"
            onPress={() => setAccount(true)}
          />
        </View>
        <View style={{ paddingHorizontal: 24, marginBottom: 24 }}>
          <Text style={[styles.muted, { marginBottom: 7 }]}>
            你好，{identity?.user.name}
          </Text>
          <Text style={styles.title}>今天，想聊些什么？</Text>
          <Text style={[styles.muted, { marginTop: 9 }]}>
            把问题交给你的智能体，一起向前一步。
          </Text>
        </View>
        <View style={{ marginBottom: 22 }}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ paddingHorizontal: 24, gap: 10 }}
          >
            {agents.map((agent) => (
              <Pressable
                key={agent.id}
                accessibilityRole="button"
                accessibilityLabel={`选择智能体 ${agent.data.name}`}
                accessibilityState={{ selected: selected === agent.id }}
                onPress={() => setSelected(agent.id)}
                style={{
                  paddingHorizontal: 18,
                  paddingVertical: 12,
                  borderRadius: 24,
                  backgroundColor: selected === agent.id ? colors.ink : "#fff",
                  borderWidth: 1,
                  borderColor: selected === agent.id ? colors.ink : colors.line,
                }}
              >
                <Text
                  style={{
                    fontSize: 14,
                    color: selected === agent.id ? "#fff" : colors.ink,
                  }}
                >
                  {agent.data.name}
                </Text>
              </Pressable>
            ))}
          </ScrollView>
        </View>
        <View style={{ paddingHorizontal: 24, marginBottom: 24 }}>
          <Action
            title="＋  新建对话"
            disabled={!selected}
            busy={creating}
            onPress={() => { void create(); }}
          />
        </View>
        <View
          style={[
            styles.row,
            {
              paddingHorizontal: 24,
              justifyContent: "space-between",
              marginBottom: 8,
            },
          ]}
        >
          <Text
            style={{ fontSize: 13, fontWeight: "600", color: colors.muted }}
          >
            最近对话
          </Text>
          <IconButton
            label="刷新会话"
            icon="refresh-outline"
            onPress={() => setRefresh((x) => x + 1)}
          />
        </View>
        <View style={{ paddingHorizontal: 24 }}>
          <Notice text={error} retry={() => setRefresh((x) => x + 1)} />
        </View>
        {loading ? (
          <ActivityIndicator color={colors.teal} style={{ marginTop: 50 }} />
        ) : (
          <FlatList
            data={sessions}
            keyExtractor={(item) => item.session.id}
            contentContainerStyle={{
              padding: 24,
              paddingTop: 4,
              gap: 10,
              paddingBottom: 32,
            }}
            refreshing={loading}
            onRefresh={() => setRefresh((x) => x + 1)}
            ListEmptyComponent={
              <View
                style={{ alignItems: "center", paddingVertical: 52, gap: 12 }}
              >
                <Ionicons
                  name="chatbubbles-outline"
                  size={40}
                  color={colors.muted}
                />
                <Text style={[styles.text, { fontWeight: "600" }]}>
                  {agents.length ? "从第一句开始" : "还没有智能体"}
                </Text>
                <Text style={[styles.muted, { textAlign: "center" }]}>
                  {agents.length
                    ? "新建一段对话，想法就有了起点。"
                    : "在桌面端创建 Agent 和模型服务后，\n即可在手机上开始对话。"}
                </Text>
              </View>
            }
            renderItem={({ item }) => (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`打开对话 ${item.session.config.name}`}
                onPress={() =>
                  openChat(item.session.id, item.session.config.name)
                }
                style={[styles.card, styles.row]}
              >
                <View
                  style={{
                    width: 38,
                    height: 38,
                    borderRadius: 12,
                    backgroundColor: colors.pale,
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Ionicons
                    name="chatbubble-ellipses-outline"
                    size={19}
                    color={colors.teal}
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Text
                    numberOfLines={1}
                    style={{
                      color: colors.ink,
                      fontSize: 15,
                      fontWeight: "600",
                    }}
                  >
                    {item.session.config.name}
                  </Text>
                  <Text
                    numberOfLines={1}
                    style={[styles.muted, { fontSize: 11, marginTop: 5 }]}
                  >
                    {item.is_running ? "正在回复 · " : ""}
                    {agentName}{" "}
                    ·{" "}
                    {new Date(item.session.updated_at).toLocaleDateString(
                      "zh-CN",
                    )}
                  </Text>
                </View>
                <Ionicons
                  name="chevron-forward"
                  size={16}
                  color={colors.muted}
                />
              </Pressable>
            )}
          />
        )}
        <Modal
          visible={account}
          transparent
          animationType="fade"
          onRequestClose={() => setAccount(false)}
        >
          <View
            style={{
              flex: 1,
              justifyContent: "center",
              backgroundColor: "#18191c80",
              padding: 28,
            }}
          >
            <View
              style={[
                styles.card,
                { gap: 16, width: "100%", maxWidth: 500, alignSelf: "center" },
              ]}
            >
              <View style={[styles.row, { justifyContent: "space-between" }]}>
                <Text
                  style={{ fontSize: 20, color: colors.ink, fontWeight: "700" }}
                >
                  工作空间
                </Text>
                <IconButton
                  icon="close"
                  label="关闭账户"
                  onPress={() => setAccount(false)}
                />
              </View>
              <Text style={styles.muted}>{identity?.user.email}</Text>
              <Notice text={error} />
              {identity?.tenants.map((t) => (
                <Pressable
                  key={t.id}
                  disabled={accountBusy}
                  onPress={() => {
                    void changeTenant(t.id);
                  }}
                  style={{
                    padding: 16,
                    borderRadius: 12,
                    backgroundColor: tenant === t.id ? colors.pale : colors.bg,
                  }}
                >
                  <Text style={styles.text}>
                    {t.name}
                    {tenant === t.id ? "  ✓" : ""}
                  </Text>
                </Pressable>
              ))}
              <Action
                title="退出登录"
                secondary
                busy={accountBusy}
                onPress={() => {
                  setAccountBusy(true);
                  void logout()
                    .catch((e) => setError(e.message))
                    .finally(() => setAccountBusy(false));
                }}
              />
            </View>
          </View>
        </Modal>
      </View>
    </SafeAreaView>
  );
}
