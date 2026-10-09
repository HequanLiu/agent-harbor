export interface SavedLogin {
  email: string;
  password: string;
}
export interface CredentialVault {
  read(): Promise<string | null>;
  write(value: string): Promise<void>;
  clear(): Promise<void>;
}
export function savedLoginStore(vault: CredentialVault, server: string) {
  return {
    async load(): Promise<SavedLogin | null> {
      const value = await vault.read();
      if (!value) return null;
      try {
        const saved = JSON.parse(value);
        if (saved.server !== server) return null;
        if (
          typeof saved.email !== "string" ||
          typeof saved.password !== "string"
        )
          throw new Error("Invalid credentials");
        return { email: saved.email, password: saved.password };
      } catch {
        await vault.clear();
        return null;
      }
    },
    async save(login: SavedLogin | null) {
      if (login) await vault.write(JSON.stringify({ server, ...login }));
      else await vault.clear();
    },
  };
}
