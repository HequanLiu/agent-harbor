import * as SecureStore from "expo-secure-store";
import type { CredentialVault } from "../core/saved-login";
const KEY = "harbor.mobile.remembered-login";
export const credentialVault: CredentialVault = {
  read: () => SecureStore.getItemAsync(KEY),
  write: (value) =>
    SecureStore.setItemAsync(KEY, value, {
      keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    }),
  clear: () => SecureStore.deleteItemAsync(KEY),
};
