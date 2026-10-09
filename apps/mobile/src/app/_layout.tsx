import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { ActivityIndicator, Text, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AuthProvider, useAuth } from "../auth/AuthProvider";
import { Action, colors, styles } from "../components/ui";
function Navigation() {
  const { identity, loading, bootError, retry, logout } = useAuth();
  if (loading || bootError)
    return (
      <View
        style={[
          styles.screen,
          {
            justifyContent: "center",
            alignItems: "center",
            padding: 30,
            gap: 20,
          },
        ]}
      >
        {loading ? (
          <ActivityIndicator color={colors.teal} />
        ) : (
          <>
            <Text style={styles.text}>{bootError}</Text>
            <Action title="重新连接" onPress={retry} />
            <Action
              title="返回登录"
              secondary
              onPress={() => {
                void logout().catch(() => {});
              }}
            />
          </>
        )}
      </View>
    );
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.bg },
        animation: "slide_from_right",
      }}
    >
      <Stack.Protected guard={!identity}>
        <Stack.Screen name="login" />
      </Stack.Protected>
      <Stack.Protected guard={!!identity}>
        <Stack.Screen name="index" />
        <Stack.Screen name="history" />
        <Stack.Screen name="chat/[id]" />
      </Stack.Protected>
    </Stack>
  );
}
export default function Layout() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <StatusBar style="dark" />
        <Navigation />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
