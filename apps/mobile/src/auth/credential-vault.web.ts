import type { CredentialVault } from "../core/saved-login";
interface EncryptedLogin {
  key: CryptoKey;
  iv: Uint8Array<ArrayBuffer>;
  data: ArrayBuffer;
}
function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("harbor-mobile-credentials", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("vault");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () =>
      reject(new Error("请关闭其他页面后重试密码存储。"));
  });
}
async function access(
  mode: IDBTransactionMode,
  operation: (store: IDBObjectStore) => IDBRequest,
): Promise<EncryptedLogin | undefined> {
  const db = await open();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction("vault", mode);
      const request = operation(tx.objectStore("vault"));
      tx.oncomplete = () =>
        resolve(request.result as EncryptedLogin | undefined);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("密码存储已中止。"));
    });
  } finally {
    db.close();
  }
}
export const credentialVault: CredentialVault = {
  async read() {
    const record = await access("readonly", (store) => store.get("login"));
    if (!record) return null;
    const bytes = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: record.iv },
      record.key,
      record.data,
    );
    return new TextDecoder().decode(bytes);
  },
  async write(value) {
    if (!globalThis.crypto?.subtle)
      throw new Error("请通过 HTTPS 或本机地址使用记住密码。");
    const key = await crypto.subtle.generateKey(
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"],
    );
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const data = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      key,
      new TextEncoder().encode(value),
    );
    await access("readwrite", (store) => store.put({ key, iv, data }, "login"));
  },
  async clear() {
    await access("readwrite", (store) => store.delete("login"));
  },
};
