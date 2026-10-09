import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { ConfirmCard } from "../../components/ConfirmCard";
import { confirmationKey } from "../../core/messages";
import { MarkdownMessage } from "../../components/MarkdownMessage";
import { BrandLogo } from "../../components/BrandLogo";
import { useAuth } from "../../auth/AuthProvider";
import { defaultChat } from "../../core/default-chat";
import { useConversation } from "../../chat/useConversation";
import { colors, IconButton, Notice, styles } from "../../components/ui";
import type { Message } from "../../core/types";
export default function Chat() {
  const params = useLocalSearchParams<{
    id: string;
    agentId: string;
    name?: string;
    agentName?: string;
    model?: string;
  }>();
  const { api } = useAuth();
  const [creating, setCreating] = useState(false);
  const createLock = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const chat = useConversation(params.agentId || "", params.id || "");
  const [draft, setDraft] = useState("");
  const [sendError, setSendError] = useState("");
  const list = useRef<FlatList<Message>>(null);
  const nearBottom = useRef(true);
  async function createChat() {
    if (createLock.current || !params.agentId) return;
    createLock.current = true;
    setCreating(true);
    setSendError("");
    const tenant = api.tenant;
    const token = api.token;
    const current = () => mounted.current && api.tenant === tenant && api.token === token;
    try {
      const next = await defaultChat(api, current, { agentId: params.agentId, sourceSessionId: params.id, createNew: true });
      if (current()) {
        setDraft("");
        router.replace({ pathname: "/chat/[id]", params: { ...next } });
      }
    } catch (e) {
      if (current()) setSendError(e instanceof Error ? e.message : "创建对话失败，请重试");
    } finally {
      createLock.current = false;
      if (mounted.current) setCreating(false);
    }
  }
  async function send() {
    const text = draft;
    if (!text.trim()) return;
    setSendError("");
    setDraft("");
    nearBottom.current = true;
    try {
      if (!(await chat.send(text))) setDraft(text);
    } catch {
      setDraft(text);
      setSendError(
        "发送未确认，已重新同步历史。请确认消息是否已发出后再重试。",
      );
    }
  }
  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: "#fff" }]}>
      <KeyboardAvoidingView
        style={styles.frame}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        <View
          style={[
            styles.row,
            {
              paddingHorizontal: 12,
              paddingVertical: 10,
              borderBottomWidth: 1,
              borderBottomColor: colors.line,
            },
          ]}
        >
          <IconButton
            icon="menu-outline"
            label="返回会话列表"
            onPress={() => {
              router.replace("/history");
            }}
          />
          <View style={[styles.row, { flex: 1, gap: 7, minWidth: 0 }]}>
            <View accessible accessibilityLabel={chat.connected ? "已连接" : "未连接"} style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: chat.connected ? "#27A185" : "#A8B1B7" }} />
            <Text numberOfLines={1} style={{ flex: 1, color: colors.ink, fontSize: 15, fontWeight: "600" }}>
              {params.agentName || "小助理"}{chat.pending || chat.confirmations.length > 0
                ? " · 等待确认" : chat.running ? " · 正在回复…" : chat.connected ? "" : " · 连接中…"}
            </Text>
          </View>
          {creating ? <ActivityIndicator style={{ width: 44 }} color={colors.primary} /> : (
            <IconButton label="新建对话" icon="create-outline" disabled={!params.agentId} onPress={() => { void createChat(); }} />
          )}
        </View>
        {chat.loading ? (
          <View style={{ flex: 1, justifyContent: "center" }}>
            <ActivityIndicator color={colors.teal} />
          </View>
        ) : (
          <FlatList
            ref={list}
            data={chat.messages.filter(
              (m) => m.role === "user" || m.role === "assistant",
            )}
            keyExtractor={(item) => item.id}
            contentContainerStyle={{
              padding: 20,
              paddingBottom: 28,
              gap: 22,
              flexGrow: 1,
            }}
            keyboardShouldPersistTaps="handled"
            onScroll={(e) => {
              const { layoutMeasurement, contentOffset, contentSize } =
                e.nativeEvent;
              nearBottom.current =
                contentSize.height -
                  contentOffset.y -
                  layoutMeasurement.height <
                140;
            }}
            scrollEventThrottle={100}
            onContentSizeChange={() => {
              if (nearBottom.current)
                list.current?.scrollToEnd({ animated: false });
            }}
            ListHeaderComponent={
              chat.hasMore ? (
                <Pressable
                  accessibilityRole="button"
                  disabled={chat.olderBusy}
                  onPress={() => {
                    nearBottom.current = false;
                    void chat.older();
                  }}
                  style={{ padding: 12, alignItems: "center" }}
                >
                  <Text style={{ color: colors.teal, fontSize: 13 }}>
                    {chat.olderBusy ? "加载中…" : "加载更早消息"}
                  </Text>
                </Pressable>
              ) : null
            }
            ListEmptyComponent={
              <View
                style={{
                  flex: 1,
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 14,
                  paddingVertical: 55,
                }}
              >
                <BrandLogo size={64} />
                <Text
                  style={{ color: colors.ink, fontSize: 21, fontWeight: "600" }}
                >
                  让想法有个开始
                </Text>
                <Text style={[styles.muted, { textAlign: "center" }]}>
                  提一个问题，聊一个想法，{"\n"}或者一起完成一件事。
                </Text>
              </View>
            }
            renderItem={({ item }) => {
              const own = item.role === "user";
              const text = item.content
                .filter((b) => b.type === "text")
                .map((b) => b.text || "")
                .join("\n");
              return (
                <View
                  style={{
                    alignItems: own ? "flex-end" : "flex-start",
                    gap: 8,
                  }}
                >
                  <Text
                    style={{
                      color: colors.muted,
                      fontSize: 10,
                      letterSpacing: 0.5,
                    }}
                  >
                    {own ? "你" : item.name || params.agentName || "智能体"}
                  </Text>
                  <View
                    style={{
                      backgroundColor: own ? colors.pale : colors.bg,
                      borderRadius: 18,
                      borderTopRightRadius: own ? 5 : 18,
                      borderTopLeftRadius: own ? 18 : 5,
                      padding: 16,
                      maxWidth: "96%",
                      width: own ? undefined : "96%",
                    }}
                  >
                    {text ? <MarkdownMessage text={text} /> : (
                      <Text selectable style={{ color: colors.ink, fontSize: 15, lineHeight: 25 }}>
                        {chat.running ? "正在思考…" : "此消息包含工具或附件内容，请在桌面端查看。"}
                      </Text>
                    )}
                  </View>
                </View>
              );
            }}
          />
        )}
        <View style={{ paddingHorizontal: 20, gap: 8 }}>
          <Notice text={sendError || chat.error} retry={chat.reconnect} />
          {chat.confirmations.length > 0 ? (
            <ScrollView style={{ maxHeight: 360 }} contentContainerStyle={{ gap: 10 }} keyboardShouldPersistTaps="handled" nestedScrollEnabled>
              {chat.confirmations.map((entry) => (
                <ConfirmCard key={confirmationKey(entry)} entry={entry}
                  busy={chat.confirming.includes(confirmationKey(entry))}
                  disabled={!chat.connected || chat.interrupting}
                  onConfirm={(approved, rules) => { void chat.confirm(entry, approved, rules); }} />
              ))}
            </ScrollView>
          ) : chat.pending ? (
            <Notice text="此工具需要桌面端执行，请在桌面端处理；也可以点击停止结束本次回复。" />
          ) : null}
        </View>
        <View style={{ padding: 16, paddingTop: 12 }}>
          <View
            style={{
              flexDirection: "row",
              alignItems: "flex-end",
              borderRadius: 22,
              backgroundColor: colors.bg,
              borderWidth: 1,
              borderColor: colors.line,
              padding: 8,
            }}
          >
            <TextInput
              accessibilityLabel="消息"
              multiline
              value={draft}
              onChangeText={setDraft}
              placeholder="给智能体发消息…"
              placeholderTextColor={colors.muted}
              maxLength={8000}
              style={{
                flex: 1,
                color: colors.ink,
                fontSize: 15,
                lineHeight: 22,
                padding: 10,
                minHeight: 42,
                maxHeight: 140,
              }}
            />
            {chat.running ? (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="停止生成"
                disabled={chat.interrupting}
                onPress={() => {
                  void chat.stop();
                }}
                style={{
                  width: 42,
                  height: 42,
                  backgroundColor: colors.ink,
                  borderRadius: 15,
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {chat.interrupting ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Ionicons name="stop" size={17} color="#fff" />
                )}
              </Pressable>
            ) : (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="发送消息"
                disabled={!draft.trim() || !chat.connected}
                onPress={() => {
                  void send();
                }}
                style={{
                  width: 42,
                  height: 42,
                  backgroundColor: colors.primary,
                  opacity: !draft.trim() || !chat.connected ? 0.35 : 1,
                  borderRadius: 15,
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Ionicons name="arrow-up" size={23} color="#fff" />
              </Pressable>
            )}
          </View>
          <Text
            style={{
              color: colors.muted,
              fontSize: 10,
              textAlign: "center",
              marginTop: 9,
            }}
          >
            AI 也会犯错，请核实重要信息
          </Text>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
