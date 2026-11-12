const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(
  path.join(__dirname, "../book/_ext/changelog_notifications_static/changelog-notifications.js"),
  "utf8",
);
const fingerprint = (character) => character.repeat(64);

function createPage(options = {}) {
  const values = options.values || new Map();
  const notifications = [];
  let manifest = options.manifest || { fingerprint: fingerprint("a"), url: "changelog.html" };
  let fetchError = null;
  let timer;
  const elements = [];
  function element() {
    const listeners = {};
    return {
      listeners,
      append(...children) { this.children = children; },
      setAttribute() {},
      addEventListener(name, callback) { listeners[name] = callback; },
    };
  }
  const document = {
    currentScript: { src: "https://example.org/book/_static/changelog-notifications.js" },
    createElement() { const result = element(); elements.push(result); return result; },
    body: { append() {} },
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
    setInterval(callback, delay) { timer = callback; assert.equal(delay, 300000); },
  };
  const localStorage = {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  const fetch = async (url, fetchOptions) => {
    assert.equal(url.href, "https://example.org/book/_static/changelog-notifications.json");
    assert.equal(fetchOptions.cache, "no-store");
    if (fetchError) throw fetchError;
    return { ok: true, json: async () => manifest };
  };
  vm.runInNewContext(script, {
    document, window, localStorage, Notification, fetch, URL,
    console: { error() {} },
  });
  return {
    button: elements[1],
    status: elements[2],
    notifications,
    values,
    window,
    tick: () => timer(),
    setManifest: (value) => { manifest = value; },
    setFetchError: (value) => { fetchError = value; },
  };
}

test("opt in, notify once on a change, and disable", async () => {
  const page = createPage();
  assert.equal(page.button.textContent, "Enable changelog notifications");
  await page.button.listeners.click();
  assert.equal(page.button.textContent, "Disable changelog notifications");
  await page.tick();
  assert.equal(page.notifications.length, 0);

  page.setManifest({ fingerprint: fingerprint("b"), url: "changelog.html" });
  await page.tick();
  await page.tick();
  assert.equal(page.notifications.length, 1);
  page.notifications[0].onclick();
  assert.equal(page.window.location.href, "https://example.org/book/changelog.html");
  await page.button.listeners.click();
  page.setManifest({ fingerprint: fingerprint("c"), url: "changelog.html" });
  await page.tick();
  assert.equal(page.notifications.length, 1);
  assert.equal(page.values.size, 0);
});

test("changes while closed are detected when a page opens", async () => {
  const first = createPage();
  await first.button.listeners.click();
  const second = createPage({
    values: first.values,
    permission: "granted",
    manifest: { fingerprint: fingerprint("b"), url: "changelog.html" },
  });
  await new Promise(setImmediate);
  assert.equal(second.notifications.length, 1);
});

test("open tabs share the last notified fingerprint", async () => {
  const first = createPage();
  await first.button.listeners.click();
  const second = createPage({ values: first.values, permission: "granted" });
  await new Promise(setImmediate);
  first.setManifest({ fingerprint: fingerprint("b"), url: "changelog.html" });
  second.setManifest({ fingerprint: fingerprint("b"), url: "changelog.html" });
  await Promise.all([first.tick(), second.tick()]);
  assert.equal(first.notifications.length + second.notifications.length, 1);
});

test("denied permission and failed checks do not enable or lose updates", async () => {
  const denied = createPage({ requestResult: "denied" });
  await denied.button.listeners.click();
  assert.equal(denied.values.size, 0);
  assert.match(denied.status.textContent, /blocked/);

  const page = createPage();
  page.setFetchError(new Error("offline"));
  await page.button.listeners.click();
  assert.equal(page.values.size, 0);
  assert.match(page.status.textContent, /try again/);
  page.setFetchError(null);
  await page.button.listeners.click();
  page.setManifest({ fingerprint: fingerprint("b"), url: "changelog.html" });
  page.setFetchError(new Error("offline"));
  await page.tick();
  assert.equal(page.notifications.length, 0);
  page.setFetchError(null);
  await page.tick();
  assert.equal(page.notifications.length, 1);
});
