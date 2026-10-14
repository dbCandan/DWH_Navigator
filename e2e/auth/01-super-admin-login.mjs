import {
  withBrowser,
  baseUrl,
  apiPrefix,
  accounts,
  message,
  signIn,
} from "../shared/harness.mjs";

await withBrowser(
  "super-admin login, memory-only token, session restore and sign-out",
  async ({ page, assert }) => {
    // anonymous-visitor Requirement 1: only the admin screen asks for the sign-in.
    await page.goto(baseUrl + "/admin");
    await page.waitForURL(baseUrl + "/login");

    // user-accounts Requirement 1, 16: the real form; a one-time password asks for a new one first.
    const firstLogin = await signIn(page, accounts.superAdmin);
    console.log(firstLogin ? "first sign-in: new password set" : "signed in with the set password");
    await page.waitForURL(baseUrl + "/admin/genel");

    // Requirement 6-7: no token or session copy in browser storage; the refresh cookie is HttpOnly,
    // strict and scoped to the auth path.
    const storage = await page.evaluate(() => ({
      local: localStorage.length,
      session: sessionStorage.length,
      cookie: document.cookie,
    }));
    assert.deepEqual(storage, { local: 0, session: 0, cookie: "" });
    const cookies = await page.context().cookies();
    const refresh = cookies.find((cookie) => cookie.name === "dwhnavigator_refresh");
    assert.ok(refresh, "refresh cookie is set");
    assert.equal(refresh.httpOnly, true);
    assert.equal(refresh.sameSite, "Strict");
    assert.equal(refresh.path, apiPrefix + "/auth");

    // The tenant header is still enforced for a bearer request; /auth/me is database backed.
    const tenantCheck = await page.evaluate(async (prefix) => {
      const refreshed = await fetch(prefix + "/auth/refresh", { method: "POST" });
      const session = await refreshed.json();
      const missing = await fetch(prefix + "/auth/me", {
        headers: { Authorization: "Bearer " + session.access_token },
      });
      const me = await fetch(prefix + "/auth/me", {
        headers: {
          Authorization: "Bearer " + session.access_token,
          "x-tenant-id": session.user.tenant_id,
        },
      });
      return { missing: missing.status, me: me.status, body: await me.json(), user: session.user };
    }, apiPrefix);
    assert.equal(tenantCheck.missing, 400);
    assert.equal(tenantCheck.me, 200);
    assert.equal(tenantCheck.body.is_super_admin, true);
    assert.equal(tenantCheck.body.public_id, tenantCheck.user.public_id);
    assert.ok(tenantCheck.body.roles.includes("super_admin"));

    // Requirement 13: a refresh request from another origin is refused.
    const foreign = await page.request.post(baseUrl + apiPrefix + "/auth/refresh", {
      headers: { Origin: "https://attacker.invalid" },
    });
    assert.equal(foreign.status(), 403);

    // A reload drops the in-memory token; the session comes back through the refresh cookie.
    await page.reload();
    await page.waitForURL(baseUrl + "/admin/genel");

    // Requirement 8, 16: "Çıkış" in the session area closes the session on the server.
    const sessionMenu = new RegExp("^" + message("session.menu").replace("{name}", ""));
    await page.getByRole("button", { name: sessionMenu }).click();
    await page.getByRole("button", { name: message("session.signOut") }).click();
    await page.waitForURL(baseUrl + "/login");
    const afterLogout = await page.evaluate(async (prefix) => {
      const response = await fetch(prefix + "/auth/refresh", { method: "POST" });
      return response.status;
    }, apiPrefix);
    assert.equal(afterLogout, 401);
    await page.goto(baseUrl + "/admin");
    await page.waitForURL(baseUrl + "/login");
  },
);
