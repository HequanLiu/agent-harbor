import { ScrollView, Text, View } from "react-native";
import type { Confirmation, PermissionRule } from "../core/types";
import { Action, colors, styles } from "./ui";

function formatInput(input: string) {
  try { return JSON.stringify(JSON.parse(input), null, 2); }
  catch { return input; }
}
export function ConfirmCard({ entry, busy, disabled, onConfirm }: {
  entry: Confirmation;
  busy: boolean;
  disabled: boolean;
  onConfirm: (approved: boolean, rules?: PermissionRule[]) => void;
}) {
  const { toolCall } = entry;
  const rule = toolCall.suggested_rules?.[0];
  return (
    <View style={[styles.card, { padding: 14, gap: 10, backgroundColor: colors.bg }]}>
      <Text style={[styles.text, { fontWeight: "700" }]}>{entry.workerName ? `${entry.workerName} · ` : ""}操作需要确认</Text>
      <Text selectable style={styles.text}>{toolCall.name}</Text>
      <ScrollView style={{ maxHeight: 120, backgroundColor: "#fff", borderRadius: 8 }} nestedScrollEnabled>
        <Text selectable style={[styles.muted, { padding: 10 }]}>{formatInput(toolCall.input)}</Text>
        {rule && <Text selectable style={[styles.muted, { padding: 10 }]}>记住规则：{rule.tool_name} · {rule.rule_content || "所有调用"}</Text>}
      </ScrollView>
      {busy ? <Text accessibilityRole="alert" style={styles.muted}>已提交，等待处理…</Text> : null}
      <View style={{ flexDirection: "row", gap: 10 }}>
        <View style={{ flex: 1 }}><Action title="允许一次" busy={busy} disabled={disabled} onPress={() => onConfirm(true)} /></View>
        <View style={{ flex: 1 }}><Action title="拒绝" secondary disabled={disabled || busy} onPress={() => onConfirm(false)} /></View>
      </View>
      {rule && <Action title="允许并记住规则" secondary disabled={disabled || busy} onPress={() => onConfirm(true, [rule])} />}
    </View>
  );
}
