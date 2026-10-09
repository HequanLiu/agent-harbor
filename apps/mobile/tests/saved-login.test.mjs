import test from "node:test";
import assert from "node:assert/strict";
import { savedLoginStore } from "../src/core/saved-login.ts";
function vault() {
  let value = null;
  return {
    read: async () => value,
    write: async (v) => {
      value = v;
    },
    clear: async () => {
      value = null;
    },
  };
}
test("remembered credentials survive restoration and explicit removal", async () => {
  const v = vault();
  const s = savedLoginStore(v, "http://localhost:8017/");
  const login = { email: "fixture@example.test", password: "fixture-password" };
  await s.save(login);
  assert.deepEqual(await s.load(), login);
  await s.save(null);
  assert.equal(await s.load(), null);
});
test("credentials are never filled into a different backend", async () => {
  const v = vault();
  await savedLoginStore(v, "https://one.example").save({
    email: "fixture@example.test",
    password: "fixture-password",
  });
  assert.equal(await savedLoginStore(v, "https://two.example").load(), null);
});
test("corrupt stored content is cleared", async () => {
  const v = vault();
  await v.write("invalid");
  const s = savedLoginStore(v, "server");
  assert.equal(await s.load(), null);
  assert.equal(await v.read(), null);
});
