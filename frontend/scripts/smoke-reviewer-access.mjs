import assert from "node:assert/strict";

const base = new URL(process.argv[2] ?? "http://127.0.0.1:18777");
assert.equal(base.hostname, "127.0.0.1", "This smoke test is restricted to loopback");
const origin = "https://review.example.test";
const post = (path, body, extra = {}) =>
  fetch(new URL(path, base), {
    method: "POST",
    headers: { Origin: origin, "Content-Type": "application/json", ...extra },
    body: JSON.stringify(body),
    redirect: "manual",
  });
assert.equal((await fetch(base, { redirect: "manual" })).status, 303);
const page = await fetch(new URL("/login", base));
assert.equal(page.status, 200);
assert.match(await page.text(), /method="post"/);
assert.equal((await fetch(new URL("/api/demo-call", base))).status, 401);
assert.equal((await post("/api/reviewer-login", { code: "wrong" })).status, 401);
assert.equal(
  (await post("/api/reviewer-login", {}, { Origin: "https://evil.example" })).status,
  403,
);
const signedIn = await post("/api/reviewer-login", {
  code: "test-only-reviewer-code-0000000000000000",
});
assert.equal(signedIn.status, 200);
const cookie = signedIn.headers.get("set-cookie");
assert.ok(cookie?.includes("Secure; HttpOnly; SameSite=Strict"));
const session = cookie.split(";")[0];
const authenticated = await fetch(base, { headers: { Cookie: session }, redirect: "manual" });
assert.equal(authenticated.status, 200);
assert.match(await authenticated.text(), /Autonomous Scheduling Command Center/);
assert.equal((await post("/api/reviewer-logout", {}, { Cookie: session })).status, 200);
assert.equal(
  (await fetch(new URL("/api/demo-call", base), { headers: { Cookie: session } })).status,
  401,
);
console.log(
  JSON.stringify({
    status: "PASS",
    boundary: "actual Node HTTP runtime; test credentials; no backend calls",
    checks: [
      "page redirect",
      "landing page",
      "API denial",
      "wrong code",
      "cross-origin denial",
      "secure session cookie",
      "authenticated UI",
      "logout replay denial",
    ],
  }),
);
