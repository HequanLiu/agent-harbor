import { useEffect, useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "../auth/AuthProvider";
import { savedLogin } from "../auth/saved-login";
import { BrandLogo } from "../components/BrandLogo";
import { Action, colors, IconButton, Notice, styles } from "../components/ui";
export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    savedLogin
      .load()
      .then((saved) => {
        if (active && saved) {
          setEmail(saved.email);
          setPassword(saved.password);
          setRemember(true);
        }
      })
      .catch(() => {
        if (active) setError("无法读取已保存的密码，请手动输入。");
      })
      .finally(() => {
        if (active) setRestoring(false);
      });
    return () => {
      active = false;
    };
  }, []);
  async function toggleRemember() {
    if (!remember) {
      setRemember(true);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await savedLogin.save(null);
      setRemember(false);
    } catch {
      setError("无法清除已保存的密码，请重试。");
    } finally {
      setBusy(false);
    }
  }
  async function submit() {
    if (busy || restoring) return;
    if (!email.trim().includes("@") || password.length < 10) {
      setError("请输入有效邮箱和至少 10 位密码。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await login(email, password, remember);
      setPassword("");
      setVisible(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "登录失败，请重试。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: "#fff" }]}>
      <KeyboardAvoidingView
        style={styles.frame}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{
            flexGrow: 1,
            padding: 28,
            justifyContent: "center",
          }}
        >
          <View style={[styles.row, { marginBottom: 46 }]}>
            <BrandLogo />
            <View>
              <Text
                style={{ color: colors.ink, fontSize: 20, fontWeight: "700" }}
              >
                AgentHarbor · 智港
              </Text>
              <Text style={styles.muted}>独立空间 · 持续记忆 · 自由扩展</Text>
            </View>
          </View>
          <Text style={[styles.muted, { marginBottom: 9 }]}>欢迎来到智港</Text>
          <Text style={[styles.title, { fontSize: 30 }]}>登录工作空间</Text>
          <Text style={[styles.muted, { marginTop: 12, marginBottom: 32 }]}>
            继续与你的智能体协作。
          </Text>
          <Text style={styles.label}>邮箱</Text>
          <TextInput
            accessibilityLabel="邮箱"
            style={[styles.input, { marginBottom: 22 }]}
            placeholder="you@company.com"
            placeholderTextColor={colors.muted}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            autoComplete="username"
            textContentType="username"
            value={email}
            onChangeText={setEmail}
            editable={!busy && !restoring}
            maxLength={254}
          />
          <Text style={styles.label}>密码</Text>
          <View style={{ position: "relative", marginBottom: 10 }}>
            <TextInput
              accessibilityLabel="密码"
              style={[styles.input, { paddingRight: 55 }]}
              placeholder="至少 10 个字符"
              placeholderTextColor={colors.muted}
              secureTextEntry={!visible}
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="current-password"
              textContentType="password"
              value={password}
              onChangeText={setPassword}
              editable={!busy && !restoring}
              maxLength={128}
              onSubmitEditing={() => {
                void submit();
              }}
            />
            <View style={{ position: "absolute", right: 4, top: 3 }}>
              <IconButton
                icon={visible ? "eye-off-outline" : "eye-outline"}
                label={visible ? "隐藏密码" : "显示密码"}
                onPress={() => setVisible(!visible)}
              />
            </View>
          </View>
          <Pressable
            accessibilityRole="checkbox"
            accessibilityLabel="记住密码"
            aria-checked={remember}
            accessibilityState={{
              checked: remember,
              disabled: busy || restoring,
            }}
            disabled={busy || restoring}
            onPress={() => {
              void toggleRemember();
            }}
            style={[
              styles.row,
              {
                minHeight: 48,
                gap: 9,
                marginBottom: 12,
                alignSelf: "flex-start",
              },
            ]}
          >
            <View
              style={{
                width: 19,
                height: 19,
                borderRadius: 5,
                borderWidth: 1,
                borderColor: remember ? colors.primary : "#a7abb2",
                backgroundColor: remember ? colors.primary : "#fff",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {remember && <Ionicons name="checkmark" size={14} color="#fff" />}
            </View>
            <Text style={{ color: colors.ink, fontSize: 14 }}>记住密码</Text>
          </Pressable>
          <Notice text={error} />
          <View style={{ marginTop: 14 }}>
            <Action
              title="登录"
              busy={busy || restoring}
              onPress={() => {
                void submit();
              }}
            />
          </View>
          <Text style={[styles.muted, { fontSize: 12, marginTop: 18 }]}>
            {remember
              ? "下次登录自动填入账号密码，取消勾选即可清除。"
              : "仅在勾选后保存账号密码。"}
          </Text>
          <Text style={[styles.muted, { fontSize: 12, marginTop: 48 }]}>
            AgentHarbor · Built with AgentScope
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
