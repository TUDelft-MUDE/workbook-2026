const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(
  path.join(__dirname, "../book/_ext/changelog_notifications_static/changelog-notifications.js"),
  "utf8",
);
const fingerprint = (character) => character.repeat(40);
const finishCheck = () => new Promise(setImmediate);

function createPage(options = {}) {
  const values = options.values || new Map();
  const sessionValues = options.sessionValues || new Map();
  const notifications = [];
  const manifest = options.manifest || {
    fingerprint: fingerprint("a"), scheme: "git-commit", url: "changelog.html",
  };
  let fetchCount = 0;
  function element() {
    const listeners = {};
    const attributes = {};
    const classes = new Set();
    return {
      listeners,
      attributes,
      classList: {
        toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); },
        contains(name) { return classes.has(name); },
      },
      replaceChildren(...children) { this.children = children; },
      setAttribute(name, value) { attributes[name] = value; },
      removeAttribute(name) { delete attributes[name]; },
      addEventListener(name, callback) { listeners[name] = callback; },
    };
  }
  const panel = element();
  const button = element();
  const menu = element();
  const status = element();
  button.disabled = true;
  status.parentElement = menu;
  panel.querySelector = (selector) => {
    if (selector === "button") return button;
    if (selector === '[role="status"]') return status;
    throw new Error(`Unexpected selector: ${selector}`);
  };
  const document = {
    currentScript: { src: "https://example.org/book/_static/changelog-notifications.js" },
    createElement() { return element(); },
    querySelector(selector) {
      assert.equal(selector, ".changelog-notifications");
      return panel;
    },
  };
  function Notification(title, notificationOptions) {
    this.title = title;
    this.options = notificationOptions;
    notifications.push(this);
  }
  Notification.permission = options.permission || "default";
  Notification.requestPermission = async () => {
    Notification.permission = options.requestResult || "granted";
    return Notification.permission;
  };
  const window = {
    Notification,
    isSecureContext: true,
    location: { href: "" },
    focus() {},
    addEventListener() {},
  };
  function storage(map) {
    return {
      getItem: (key) => map.get(key) || null,
      setItem: (key, value) => map.set(key, value),
      removeItem: (key) => map.delete(key),
    };
  }
  const fetch = async (url, fetchOptions) => {
    fetchCount++;
    assert.equal(url.href, "https://example.org/book/_static/changelog-notifications.json");
    assert.equal(fetchOptions.cache, "no-store");
    if (options.fetchError) throw new Error("offline");
    return { ok: true, json: async () => manifest };
  };
  vm.runInNewContext(script, {
    document, window, localStorage: storage(values), sessionStorage: storage(sessionValues),
    Notification, fetch, URL, console: { error() {} },
  });
  return {
    panel,
    button,
    status,
    menu,
    notifications,
    values,
    sessionValues,
    window,
    get fetchCount() { return fetchCount; },
  };
}

test("top-bar button switches between opt-in and opt-out", async () => {
  const page = createPage();
  assert.equal(page.button.disabled, false);
  assert.equal(page.button.attributes["aria-label"], "Enable changelog notifications");
  assert.equal(page.button.attributes["aria-pressed"], "false");
  assert.equal(page.button.children[0].className, "fa-solid fa-bell-slash");
  await page.button.listeners.click();
  assert.equal(page.fetchCount, 1);
  assert.equal(page.button.attributes["aria-label"], "Disable changelog notifications");
  assert.equal(page.button.attributes["aria-pressed"], "true");
  assert.equal(page.button.children[0].className, "fa-solid fa-bell");
  await page.button.listeners.click();
  assert.equal(page.values.size, 0);
  assert.equal(page.button.attributes["aria-label"], "Enable changelog notifications");
});

test("checks once per tab session, not on subsequent pages", async () => {
  const first = createPage();
  await first.button.listeners.click();
  const updated = { fingerprint: fingerprint("b"), scheme: "git-commit", url: "changelog.html" };
  const nextPage = createPage({
    values: first.values, sessionValues: first.sessionValues, permission: "granted", manifest: updated,
  });
  await finishCheck();
  assert.equal(nextPage.fetchCount, 0);
  assert.equal(nextPage.notifications.length, 0);

  const newSession = createPage({ values: first.values, permission: "granted", manifest: updated });
  await finishCheck();
  assert.equal(newSession.fetchCount, 1);
  assert.equal(newSession.notifications.length, 1);
  newSession.notifications[0].onclick();
  assert.equal(newSession.window.location.href, "https://example.org/book/changelog.html");
  const anotherPage = createPage({
    values: first.values, sessionValues: newSession.sessionValues, permission: "granted", manifest: updated,
  });
  await finishCheck();
  assert.equal(anotherPage.fetchCount, 0);
});

test("tabs share the last notified fingerprint", async () => {
  const first = createPage();
  await first.button.listeners.click();
  const options = {
    values: first.values, permission: "granted",
    manifest: { fingerprint: fingerprint("b"), scheme: "git-commit", url: "changelog.html" },
  };
  const second = createPage(options);
  const third = createPage(options);
  await finishCheck();
  assert.equal(second.notifications.length + third.notifications.length, 1);
});

test("denied permission and failed checks do not enable or lose updates", async () => {
  const denied = createPage({ requestResult: "denied" });
  await denied.button.listeners.click();
  assert.equal(denied.values.size, 0);
  assert.match(denied.status.textContent, /blocked/);
  assert.equal(denied.menu.classList.contains("show"), true);

  const offline = createPage({ fetchError: true });
  await offline.button.listeners.click();
  assert.equal(offline.values.size, 0);
  assert.match(offline.status.textContent, /try again/);

  const enabled = createPage();
  await enabled.button.listeners.click();
  const options = {
    values: enabled.values, permission: "granted",
    manifest: { fingerprint: fingerprint("b"), scheme: "git-commit", url: "changelog.html" },
  };
  const failed = createPage({ ...options, fetchError: true });
  await finishCheck();
  assert.match(failed.status.textContent, /retry/);
  const retry = createPage({ ...options, sessionValues: failed.sessionValues });
  await finishCheck();
  assert.equal(retry.notifications.length, 1);
});

test("updates the theme tooltip when the button state changes", async () => {
  const page = createPage();
  let tooltipText = "";
  page.window.bootstrap = {
    Tooltip: { getInstance: () => ({ setContent: (content) => { tooltipText = content[".tooltip-inner"]; } }) },
  };
  await page.button.listeners.click();
  assert.equal(tooltipText, "Disable changelog notifications");
  assert.equal(page.button.attributes["data-bs-original-title"], tooltipText);
  await page.button.listeners.click();
  assert.equal(tooltipText, "Enable changelog notifications");
});

test("migrates a legacy content fingerprint without a false notification", async () => {
  const key = "changelog-notifications:https://example.org/book/";
  const values = new Map([[key, JSON.stringify({ fingerprint: "a".repeat(64) })]]);
  const migrated = createPage({ values, permission: "granted" });
  await finishCheck();
  assert.equal(migrated.notifications.length, 0);
  assert.deepEqual(JSON.parse(values.get(key)), {
    fingerprint: fingerprint("a"), scheme: "git-commit",
  });
  const changed = createPage({
    values, permission: "granted",
    manifest: { fingerprint: "b".repeat(64), scheme: "git-commit", url: "changelog.html" },
  });
  await finishCheck();
  assert.equal(changed.notifications.length, 1);
});

test("rejects malformed commit fingerprints", async () => {
  const page = createPage({ manifest: {
    fingerprint: "a".repeat(41), scheme: "git-commit", url: "changelog.html",
  } });
  await page.button.listeners.click();
  assert.equal(page.values.size, 0);
  assert.match(page.status.textContent, /try again/);
});
