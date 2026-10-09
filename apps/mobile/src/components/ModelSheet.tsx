import { useEffect, useState } from "react";
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "../auth/AuthProvider";
import type { CredentialChoice, ModelChoice, ModelConfig } from "../core/types";
import { Action, colors, IconButton, Notice, styles } from "./ui";
export function ModelSheet({
  initial,
  close,
  create,
}: {
  initial?: ModelConfig | null;
  close: () => void;
  create: (model: ModelConfig) => Promise<void>;
}) {
  const { api } = useAuth();
  const inset = useSafeAreaInsets();
  const [credentials, setCredentials] = useState<CredentialChoice[]>([]);
  const [credential, setCredential] = useState(initial?.credential_id || "");
  const [model, setModel] = useState(initial?.model || "");
  const [models, setModels] = useState<ModelChoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api
      .credentials()
      .then((result) => {
        if (active) {
          setCredentials(result.credentials);
          setCredential((previous) =>
            result.credentials.some((c) => c.id === previous)
              ? previous
              : result.credentials[0]?.id || "",
          );
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [api]);
  const selected = credentials.find((c) => c.id === credential);
  // Clear stale network state when the subscription or resource changes.
  useEffect(() => {
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setModels([]);
    if (selected)
      api
        .models(selected.type)
        .then((result) => {
          if (active)
            setModels(result.models.filter((m) => m.status !== "sunset"));
        })
        .catch(() => {});
    return () => {
      active = false;
    };
  }, [api, selected]);
  async function submit() {
    if (!selected || !model.trim()) return;
    setBusy(true);
    setError("");
    try {
      await create({
        type: selected.type,
        credential_id: selected.id,
        model: model.trim(),
        parameters:
          initial?.model === model && initial.credential_id === selected.id
            ? initial.parameters
            : {},
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      transparent
      animationType="slide"
      onRequestClose={() => {
        if (!busy) close();
      }}
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={{
          flex: 1,
          justifyContent: "flex-end",
          backgroundColor: "#18191c80",
        }}
      >
        <View
          style={{
            backgroundColor: colors.bg,
            borderTopLeftRadius: 26,
            borderTopRightRadius: 26,
            padding: 24,
            paddingBottom: Math.max(24, inset.bottom),
            maxHeight: "90%",
            width: "100%",
            maxWidth: 640,
            alignSelf: "center",
          }}
        >
          <View
            style={[
              styles.row,
              { justifyContent: "space-between", marginBottom: 8 },
            ]}
          >
            <Text
              style={{ color: colors.ink, fontSize: 22, fontWeight: "700" }}
            >
              开始新对话
            </Text>
            <IconButton
              label="关闭新对话"
              icon="close"
              onPress={close}
              disabled={busy}
            />
          </View>
          <Text style={[styles.muted, { marginBottom: 24 }]}>
            使用桌面端已配置的模型，继续你的工作。
          </Text>
          <ScrollView keyboardShouldPersistTaps="handled">
            <Text style={styles.label}>模型服务</Text>
            <View style={{ gap: 8, marginBottom: 22 }}>
              {credentials.map((item) => (
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{ selected: credential === item.id }}
                  onPress={() => {
                    setCredential(item.id);
                    setModel("");
                  }}
                  key={item.id}
                  disabled={busy}
                  style={[
                    styles.card,
                    {
                      padding: 14,
                      borderColor:
                        credential === item.id ? colors.teal : colors.line,
                      backgroundColor:
                        credential === item.id ? colors.pale : "#fff",
                    },
                  ]}
                >
                  <Text style={styles.text}>{item.name || item.type}</Text>
                </Pressable>
              ))}
            </View>
            {!loading && credentials.length === 0 && (
              <Text style={styles.muted}>
                尚无模型服务，请先在桌面端添加模型凭据，再回到这里刷新。
              </Text>
            )}
            <Text style={styles.label}>模型名称</Text>
            <TextInput
              accessibilityLabel="模型名称"
              style={styles.input}
              value={model}
              onChangeText={setModel}
              autoCapitalize="none"
              autoCorrect={false}
              editable={!busy}
              placeholder="选择下方模型，或输入自定义模型名"
              placeholderTextColor={colors.muted}
              maxLength={200}
            />
            <View
              style={{
                flexDirection: "row",
                flexWrap: "wrap",
                gap: 8,
                marginVertical: 16,
              }}
            >
              {models
                .filter(
                  (m) =>
                    !model ||
                    m.name.toLowerCase().includes(model.toLowerCase()),
                )
                .slice(0, 8)
                .map((item) => (
                  <Pressable
                    key={item.name}
                    accessibilityRole="button"
                    onPress={() => setModel(item.name)}
                    style={{
                      borderRadius: 9,
                      padding: 10,
                      backgroundColor: colors.pale,
                    }}
                  >
                    <Text style={{ color: colors.ink, fontSize: 12 }}>
                      {item.label || item.name}
                    </Text>
                  </Pressable>
                ))}
            </View>
            <Notice text={error} />
          </ScrollView>
          <View style={{ marginTop: 20 }}>
            <Action
              title="创建对话"
              busy={busy || loading}
              disabled={!selected || !model.trim()}
              onPress={() => {
                void submit();
              }}
            />
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
