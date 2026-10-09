import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import { API_URL } from "../api/config";
const KEY = "harbor.mobile.session";
export async function loadToken(): Promise<string | null> {
  if (Platform.OS === "web") return null;
  const value = await SecureStore.getItemAsync(KEY);
  if (!value) return null;
  try {
    const saved = JSON.parse(value);
    return saved.server === API_URL && typeof saved.token === "string"
      ? saved.token
      : null;
  } catch {
    await SecureStore.deleteItemAsync(KEY);
    return null;
  }
}
export async function storeToken(token: string | null) {
  if (Platform.OS === "web") return;
  if (token)
    await SecureStore.setItemAsync(
      KEY,
      JSON.stringify({ server: API_URL, token }),
      { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY },
    );
  else await SecureStore.deleteItemAsync(KEY);
}
