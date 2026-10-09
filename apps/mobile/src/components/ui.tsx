import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { ComponentProps } from "react";
export const colors = {
  ink: "#18191c",
  primary: "#18191c",
  muted: "#6b6f76",
  teal: "#0d9488",
  pale: "#f7f8f9",
  bg: "#f4f5f6",
  line: "#e5e7eb",
  red: "#AE3D3D",
};
export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  frame: { flex: 1, width: "100%", maxWidth: 640, alignSelf: "center" },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  title: {
    color: colors.ink,
    fontSize: 28,
    fontWeight: "700",
    letterSpacing: -0.8,
  },
  text: { color: colors.ink, fontSize: 15, lineHeight: 23 },
  muted: { color: colors.muted, fontSize: 13, lineHeight: 21 },
  input: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 14,
    paddingHorizontal: 16,
    paddingVertical: 14,
    color: colors.ink,
    fontSize: 16,
    minHeight: 50,
  },
  label: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "600",
    marginBottom: 9,
  },
  card: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 18,
    padding: 18,
  },
});
export function Action({
  title,
  onPress,
  busy = false,
  disabled = false,
  secondary = false,
}: {
  title: string;
  onPress: () => void;
  busy?: boolean;
  disabled?: boolean;
  secondary?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => ({
        backgroundColor: secondary ? colors.pale : colors.primary,
        borderRadius: 14,
        minHeight: 50,
        paddingHorizontal: 20,
        justifyContent: "center",
        alignItems: "center",
        opacity: disabled || busy ? 0.5 : pressed ? 0.8 : 1,
      })}
    >
      {busy ? (
        <ActivityIndicator color={secondary ? colors.primary : "#fff"} />
      ) : (
        <Text
          style={{
            color: secondary ? colors.primary : "#fff",
            fontWeight: "600",
            fontSize: 15,
          }}
        >
          {title}
        </Text>
      )}
    </Pressable>
  );
}
export function IconButton({
  icon,
  label,
  onPress,
  disabled = false,
}: {
  icon: ComponentProps<typeof Ionicons>["name"];
  label: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => ({
        width: 44,
        height: 44,
        borderRadius: 14,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: pressed ? colors.pale : "transparent",
        opacity: disabled ? 0.4 : 1,
      })}
    >
      <Ionicons name={icon} size={22} color={colors.ink} />
    </Pressable>
  );
}
export function Notice({ text, retry }: { text?: string; retry?: () => void }) {
  if (!text) return null;
  return (
    <View
      style={{
        padding: 14,
        borderRadius: 12,
        backgroundColor: "#FFF0EC",
        gap: 8,
      }}
    >
      <Text
        accessibilityRole="alert"
        style={{ color: colors.red, fontSize: 13, lineHeight: 20 }}
      >
        {text}
      </Text>
      {retry && (
        <Pressable
          onPress={retry}
          accessibilityRole="button"
          accessibilityLabel="重试"
          style={{ minHeight: 36, justifyContent: "center" }}
        >
          <Text style={{ color: colors.teal, fontWeight: "700" }}>重试</Text>
        </Pressable>
      )}
    </View>
  );
}
