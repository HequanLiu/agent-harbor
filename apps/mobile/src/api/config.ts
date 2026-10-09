import { Platform } from "react-native";
const configured = process.env.EXPO_PUBLIC_API_URL?.trim();
// Keep local browser requests same-site: localhost and 127.0.0.1 differ.
const localHost = Platform.OS === "web" && typeof window !== "undefined" && window.location.hostname === "localhost"
  ? "localhost" : "127.0.0.1";
export const API_URL = configured || (Platform.OS === "android"
  ? "http://10.0.2.2:8017/" : `http://${localHost}:8017/`);
