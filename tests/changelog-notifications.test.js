const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(
  path.join(__dirname, "../book/_ext/changelog_notifications_static/changelog-notifications.js"),
  "utf8",
);
const workerScript = fs.readFileSync(
  path.join(__dirname, "../book/_ext/changelog_notifications_static/changelog-notifications-worker.js"),
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
  let permissionRequests = 0;
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
        add(name) { classes.add(name); },
        remove(name) { classes.delete(name); },
      },
      matches(selector) { return selector === ":hover" && this.hover; },
      replaceChildren(...children) { this.children = children; },
      setAttribute(name, value) { attributes[name] = value; },
      removeAttribute(name) { delete attributes[name]; },
      addEventListener(name, callback) { listeners[name] = callback; },
      focus() { this.focused = true; },
    };
  }
  const panel = element();
  const button = element();
  const menu = element();
  const status = element();
  const statusContainer = element();
  const statusClose = element();
  const intro = element();
  const toggleButton = element();
  const toggleIcon = element();
  const toggleLabel = element();
  const introDismiss = element();
  button.disabled = true;
  statusContainer.hidden = true;
  intro.hidden = true;
  panel.querySelector = (selector) => {
    if (selector === "button") return button;
    if (selector === ".changelog-notifications-menu") return menu;
    if (selector === '[role="status"]') return status;
    if (selector === ".changelog-notifications-status") return statusContainer;
    if (selector === "[data-changelog-status-close]") return statusClose;
    if (selector === ".changelog-notifications-intro") return intro;
    if (selector === "[data-changelog-toggle]") return toggleButton;
    if (selector === "[data-changelog-toggle-icon]") return toggleIcon;
    if (selector === "[data-changelog-toggle-label]") return toggleLabel;
    if (selector === "[data-changelog-dismiss]") return introDismiss;
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
    permissionRequests++;
    Notification.permission = options.requestResult || "granted";
    return Notification.permission;
  };
  const windowListeners = {};
  const window = {
    Notification,
    isSecureContext: true,
    location: { href: "" },
    focus() {},
    addEventListener(name, callback) { windowListeners[name] = callback; },
  };
  function storage(map) {
    return {
      getItem: (key) => map.get(key) || null,
      setItem: (key, value) => {
        if (options.storageError) throw new Error("storage unavailable");
        map.set(key, value);
      },
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
    Notification, fetch, URL, navigator: options.navigator || {}, console: { error() {} },
  });
  return {
    panel,
    button,
    toggleButton,
    toggleIcon,
    toggleLabel,
    status,
    statusClose,
    menu,
    intro,
    introDismiss,
    notifications,
    values,
    sessionValues,
    window,
    windowListeners,
    get fetchCount() { return fetchCount; },
    get permissionRequests() { return permissionRequests; },
  };
}

test("menu item switches between opt-in and opt-out", async () => {
  const page = createPage();
  assert.equal(page.button.disabled, false);
  assert.equal(page.button.attributes["aria-label"], "Changelog notification settings");
  assert.equal(page.toggleButton.attributes["aria-pressed"], "false");
  assert.equal(page.toggleLabel.textContent, "Enable notifications");
  assert.equal(page.toggleIcon.children[0].className, "fa-solid fa-bell");
  assert.equal(page.button.children[0].className, "fa-solid fa-bell-slash");
  assert.equal(page.menu.classList.contains("show"), true);
  assert.equal(page.button.attributes["aria-expanded"], "true");
  page.panel.hover = true;
  await page.toggleButton.listeners.click();
  assert.equal(page.fetchCount, 1);
  assert.equal(page.toggleLabel.textContent, "Disable notifications");
  assert.equal(page.toggleButton.attributes["aria-pressed"], "true");
  assert.equal(page.button.children[0].className, "fa-solid fa-bell");
  assert.equal(page.toggleIcon.children[0].className, "fa-solid fa-bell-slash");
  assert.equal(page.menu.classList.contains("show"), false);
  assert.equal(page.button.attributes["aria-expanded"], "false");
  assert.equal(page.panel.classList.contains("hover-dismissed"), true);
  await page.toggleButton.listeners.click();
  assert.equal(page.values.has("changelog-notifications:https://example.org/book/"), false);
  assert.equal(page.toggleLabel.textContent, "Enable notifications");
  assert.equal(page.toggleIcon.children[0].className, "fa-solid fa-bell");
});

test("notifies once per tab session; later pages silently refresh the stored commit", async () => {
  const first = createPage();
  await first.toggleButton.listeners.click();
  const updated = { fingerprint: fingerprint("b"), scheme: "git-commit", url: "changelog.html" };
  const nextPage = createPage({
    values: first.values, sessionValues: first.sessionValues, permission: "granted", manifest: updated,
  });
  await finishCheck();
  assert.equal(nextPage.notifications.length, 0);
  assert.equal(JSON.parse(first.values.get([...first.values.keys()].find((key) => !key.endsWith(":intro-dismissed")))).fingerprint, fingerprint("b"));

  const newer = { ...updated, fingerprint: fingerprint("c") };
  const newSession = createPage({ values: first.values, permission: "granted", manifest: newer });
  await finishCheck();
  assert.equal(newSession.fetchCount, 1);
  assert.equal(newSession.notifications.length, 1);
  newSession.notifications[0].onclick();
  assert.equal(newSession.window.location.href, "https://example.org/book/changelog.html");
  const anotherPage = createPage({
    values: first.values, sessionValues: newSession.sessionValues, permission: "granted", manifest: newer,
  });
  await finishCheck();
  assert.equal(anotherPage.notifications.length, 0);

  const revisit = createPage({ values: first.values, permission: "granted", manifest: newer });
  await finishCheck();
  assert.equal(revisit.notifications.length, 0);
});

test("tabs share the last notified fingerprint", async () => {
  const first = createPage();
  await first.toggleButton.listeners.click();
  const options = {
    values: first.values, permission: "granted",
    manifest: { fingerprint: fingerprint("b"), scheme: "git-commit", url: "changelog.html" },
  };
  const second = createPage(options);
  const third = createPage(options);
  await finishCheck();
  assert.equal(second.notifications.length + third.notifications.length, 1);
});

function workerNavigator(options = {}) {
  const notifications = [];
  const registration = {
    active: options.worker || { state: "activated" },
    async showNotification(title, notificationOptions) {
      if (options.deliveryError) throw new Error("delivery failed");
      notifications.push({ title, options: notificationOptions });
    },
  };
  const serviceWorker = {
    async getRegistrations() { return options.existing || []; },
    async register(url, registerOptions) {
      assert.equal(url, "https://example.org/book/_static/changelog-notifications-worker.js");
      assert.equal(registerOptions.scope, "https://example.org/book/_static/changelog-notifications-worker/");
      if (options.registrationError) throw new Error("registration failed");
      return registration;
    },
  };
  return { navigator: { serviceWorker }, notifications };
}

test("delivers changed changelogs through a narrowly scoped service worker", async () => {
  const initial = createPage();
  await initial.toggleButton.listeners.click();
  const worker = workerNavigator();
  const page = createPage({
    ...worker, values: initial.values, permission: "granted",
    manifest: { fingerprint: fingerprint("b"), scheme: "git-commit", url: "changes/" },
  });
  await finishCheck();
  assert.equal(page.notifications.length, 0);
  assert.equal(worker.notifications.length, 1);
  assert.equal(worker.notifications[0].title, "Workbook changelog updated");
  assert.equal(worker.notifications[0].options.body, "Open the changelog to see what has changed.");
  assert.equal(worker.notifications[0].options.data.url, "https://example.org/book/changes/");
  assert.equal(JSON.parse(initial.values.get("changelog-notifications:https://example.org/book/")).fingerprint, fingerprint("b"));
});

test("worker registration, activation and delivery failures preserve updates for retry", async () => {
  for (const options of [
    { registrationError: true },
    { deliveryError: true },
    { worker: {
      state: "redundant", addEventListener() {}, removeEventListener() {},
    } },
    { existing: [{
      scope: "https://example.org/book/_static/changelog-notifications-worker/",
      active: { scriptURL: "https://example.org/book/unrelated-worker.js" },
    }] },
  ]) {
    const initial = createPage();
    await initial.toggleButton.listeners.click();
    const stateKey = "changelog-notifications:https://example.org/book/";
    const manifest = { fingerprint: fingerprint("b"), scheme: "git-commit", url: "changelog.html" };
    const failed = createPage({ ...workerNavigator(options), values: initial.values, permission: "granted", manifest });
    await finishCheck();
    assert.match(failed.status.textContent, /Could not show the changelog notification.*retry/);
    assert.equal(JSON.parse(failed.values.get(stateKey)).fingerprint, fingerprint("a"));
    assert.equal(failed.sessionValues.has(`${stateKey}:checked`), false);
    const worker = workerNavigator();
    createPage({ ...worker, values: initial.values, sessionValues: failed.sessionValues, permission: "granted", manifest });
    await finishCheck();
    assert.equal(worker.notifications.length, 1);
  }
});

test("worker delivery waits for activation and honors disabling while it waits", async () => {
  let stateChange;
  const worker = {
    state: "installing",
    addEventListener(name, callback) { stateChange = callback; },
    removeEventListener() {},
  };
  const initial = createPage();
  await initial.toggleButton.listeners.click();
  const delivery = workerNavigator({ worker });
  const page = createPage({
    ...delivery, values: initial.values, permission: "granted",
    manifest: { fingerprint: fingerprint("b"), scheme: "git-commit", url: "changelog.html" },
  });
  await finishCheck();
  assert.equal(delivery.notifications.length, 0);
  await page.toggleButton.listeners.click();
  worker.state = "activated";
  stateChange();
  await finishCheck();
  assert.equal(delivery.notifications.length, 0);
  assert.equal(page.values.has("changelog-notifications:https://example.org/book/"), false);
});

test("worker checks use a cross-tab lock when available", async () => {
  const initial = createPage();
  await initial.toggleButton.listeners.click();
  const worker = workerNavigator();
  let queue = Promise.resolve();
  worker.navigator.locks = {
    request(key, callback) {
      assert.equal(key, "changelog-notifications:https://example.org/book/");
      queue = queue.then(callback);
      return queue;
    },
  };
  const options = {
    ...worker, values: initial.values, permission: "granted",
    manifest: { fingerprint: fingerprint("b"), scheme: "git-commit", url: "changelog.html" },
  };
  createPage(options);
  createPage(options);
  await finishCheck();
  assert.equal(worker.notifications.length, 1);
});

test("worker notification clicks navigate a workbook window or open a new one", async () => {
  const listeners = {};
  const opened = [];
  const navigated = [];
  let focused = false;
  let closed = false;
  let windows = [{
    url: "https://example.org/book/page.html",
    async navigate(url) { navigated.push(url); return this; },
    async focus() { focused = true; },
  }];
  const self = {
    location: { href: "https://example.org/book/_static/changelog-notifications-worker.js" },
    addEventListener(name, callback) { listeners[name] = callback; },
    clients: {
      async matchAll() { return windows; },
      async openWindow(url) { opened.push(url); },
    },
  };
  vm.runInNewContext(workerScript, { self, URL });
  async function click(url) {
    let task;
    listeners.notificationclick({
      notification: { data: { url }, close() { closed = true; } },
      waitUntil(promise) { task = promise; },
    });
    return task;
  }
  await click("https://example.org/book/changelog.html");
  assert.equal(closed, true);
  assert.deepEqual(navigated, ["https://example.org/book/changelog.html"]);
  assert.equal(focused, true);
  windows = [{ url: "https://example.org/another-book/page.html" }];
  await click("https://example.org/book/changelog/");
  assert.deepEqual(opened, ["https://example.org/book/changelog/"]);
  await assert.rejects(click("https://elsewhere.example/changelog.html"), /Invalid changelog/);
  await assert.rejects(click("https://example.org/book-other/changelog.html"), /Invalid changelog/);
});

test("denied permission and failed checks do not enable or lose updates", async () => {
  const denied = createPage({ requestResult: "denied" });
  await denied.toggleButton.listeners.click();
  assert.equal(denied.values.has("changelog-notifications:https://example.org/book/"), false);
  assert.match(denied.status.textContent, /Allow them for this site in your browser's site settings/);
  assert.match(denied.status.textContent, /icon next to the address bar/);
  assert.equal(denied.menu.classList.contains("show"), true);

  const offline = createPage({ fetchError: true });
  await offline.toggleButton.listeners.click();
  assert.equal(offline.values.has("changelog-notifications:https://example.org/book/"), false);
  assert.match(offline.status.textContent, /try again/);

  const enabled = createPage();
  await enabled.toggleButton.listeners.click();
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

test("a dismissed permission request explains how to retry or find site settings", async () => {
  const page = createPage({ requestResult: "default" });
  await page.toggleButton.listeners.click();
  assert.equal(page.values.has("changelog-notifications:https://example.org/book/"), false);
  assert.equal(page.fetchCount, 0);
  assert.match(page.status.textContent, /Try the bell again/);
  assert.match(page.status.textContent, /If no prompt appears, check your browser's site settings/);
  assert.equal(page.menu.classList.contains("show"), true);
});

test("blocked guidance appears only on the first page of a tab session and can be closed", async () => {
  const first = createPage({ permission: "denied", requestResult: "denied" });
  assert.equal(first.menu.classList.contains("show"), true);
  assert.equal(first.menu.classList.contains("has-message"), true);
  assert.equal(first.statusClose.hidden, false);
  first.statusClose.listeners.click();
  assert.equal(first.menu.classList.contains("show"), false);
  assert.equal(first.menu.classList.contains("has-message"), false);
  assert.equal(first.statusClose.hidden, true);
  assert.equal(first.button.focused, true);

  const later = createPage({
    values: first.values, sessionValues: first.sessionValues, permission: "denied", requestResult: "denied",
  });
  assert.equal(later.menu.classList.contains("show"), false);
  await later.toggleButton.listeners.click();
  assert.match(later.status.textContent, /Notifications are blocked/);
  assert.equal(later.statusClose.hidden, false);
  assert.equal(later.menu.classList.contains("show"), true);

  const newSession = createPage({ values: first.values, permission: "denied" });
  assert.equal(newSession.menu.classList.contains("show"), true);
});

test("blocked guidance is not shown automatically after the first page if permission changes", () => {
  const first = createPage();
  const later = createPage({
    values: first.values, sessionValues: first.sessionValues, permission: "denied",
  });
  assert.equal(later.menu.classList.contains("show"), false);
});

test("after browser permission is allowed, prompt once to finish enabling notifications", async () => {
  const key = "changelog-notifications:https://example.org/book/";
  const first = createPage({ requestResult: "denied" });
  await first.toggleButton.listeners.click();
  const allowed = createPage({
    values: first.values, sessionValues: first.sessionValues, permission: "granted",
  });
  assert.equal(allowed.menu.classList.contains("show"), true);
  assert.match(allowed.status.textContent, /Select Enable notifications/);
  assert.equal(allowed.menu.classList.contains("has-message"), true);
  assert.equal(allowed.statusClose.hidden, false);
  assert.equal(allowed.toggleLabel.textContent, "Enable notifications");
  assert.equal(allowed.toggleIcon.children[0].className, "fa-solid fa-bell");
  assert.equal(allowed.values.has(key), false);
  assert.equal(allowed.fetchCount, 0);
  allowed.statusClose.listeners.click();
  assert.equal(allowed.menu.classList.contains("show"), false);

  const later = createPage({
    values: first.values, sessionValues: first.sessionValues, permission: "granted",
  });
  assert.equal(later.menu.classList.contains("show"), false);
  await later.toggleButton.listeners.click();
  assert.equal(later.toggleLabel.textContent, "Disable notifications");
  assert.equal(later.values.has(key), true);
  assert.equal(later.menu.classList.contains("show"), false);
});

test("already enabled subscribers are not prompted when browser permission is restored", async () => {
  const first = createPage();
  await first.toggleButton.listeners.click();
  const blocked = createPage({
    values: first.values, sessionValues: first.sessionValues, permission: "denied",
  });
  const restored = createPage({
    values: blocked.values, sessionValues: blocked.sessionValues, permission: "granted",
  });
  await finishCheck();
  assert.equal(restored.menu.classList.contains("show"), false);
  assert.equal(restored.toggleLabel.textContent, "Disable notifications");
  assert.equal(restored.status.textContent, "");
});

test("manually allowing permission after a dismissed request offers the enable action", async () => {
  const first = createPage({ requestResult: "default" });
  await first.toggleButton.listeners.click();
  const restored = createPage({
    values: first.values, sessionValues: first.sessionValues, permission: "granted",
  });
  assert.equal(restored.menu.classList.contains("show"), true);
  assert.match(restored.status.textContent, /Select Enable notifications/);
  assert.equal(restored.permissionRequests, 0);
});

test("the menu item label and icon change with notification state", async () => {
  const page = createPage();
  assert.equal(page.menu.classList.contains("show"), true);
  assert.equal(page.toggleLabel.textContent, "Enable notifications");
  await page.toggleButton.listeners.click();
  assert.equal(page.toggleLabel.textContent, "Disable notifications");
  assert.equal(page.toggleIcon.children[0].className, "fa-solid fa-bell-slash");
});

test("hover is transient and clicking closed suppresses hover until pointer leaves", () => {
  const key = "changelog-notifications:https://example.org/book/:intro-dismissed";
  const page = createPage({ values: new Map([[key, "1"]]) });
  page.panel.hover = true;
  page.panel.listeners.mouseenter();
  assert.equal(page.button.attributes["aria-expanded"], "true");

  page.menu.classList.toggle("show", true);
  page.panel.classList.toggle("show", true);
  page.button.listeners["shown.bs.dropdown"]();
  page.button.listeners["hide.bs.dropdown"]();
  page.menu.classList.toggle("show", false);
  page.panel.classList.toggle("show", false);
  page.button.setAttribute("aria-expanded", "false");
  assert.equal(page.panel.classList.contains("hover-dismissed"), true);

  page.panel.hover = false;
  page.panel.listeners.mouseleave();
  assert.equal(page.panel.classList.contains("hover-dismissed"), false);
  assert.equal(page.button.attributes["aria-expanded"], "false");
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
  const key = "changelog-notifications:https://example.org/book/";
  const page = createPage({ manifest: {
    fingerprint: "a".repeat(41), scheme: "git-commit", url: "changelog.html",
  }, values: new Map([[key, JSON.stringify({ fingerprint: fingerprint("a"), scheme: "git-commit" })]]), permission: "granted" });
  await finishCheck();
  assert.equal(page.values.get(key), JSON.stringify({ fingerprint: fingerprint("a"), scheme: "git-commit" }));
  assert.match(page.status.textContent, /retry/);
});

test("first-visit prompt can be dismissed without requesting permission", () => {
  const page = createPage();
  assert.equal(page.intro.hidden, false);
  assert.equal(page.menu.classList.contains("has-message"), true);
  assert.equal(page.menu.classList.contains("show"), true);
  assert.equal(page.permissionRequests, 0);
  page.introDismiss.listeners.click();
  assert.equal(page.intro.hidden, true);
  assert.equal(page.menu.classList.contains("has-message"), false);
  assert.equal(page.permissionRequests, 0);
  const later = createPage({ values: page.values });
  assert.equal(later.intro.hidden, true);
  assert.equal(later.button.disabled, false);
});

test("enabling from the prompt requests permission and hides it on later visits", async () => {
  const page = createPage();
  await page.toggleButton.listeners.click();
  assert.equal(page.permissionRequests, 1);
  assert.equal(page.intro.hidden, true);
  assert.equal(page.toggleButton.attributes["aria-pressed"], "true");
  const later = createPage({ values: page.values, permission: "granted" });
  assert.equal(later.intro.hidden, true);
  await later.toggleButton.listeners.click();
  assert.equal(later.intro.hidden, true);
});

test("another tab's dismissal hides the prompt", () => {
  const first = createPage();
  const second = createPage({ values: first.values });
  first.introDismiss.listeners.click();
  second.windowListeners.storage({ key: "changelog-notifications:https://example.org/book/:intro-dismissed" });
  assert.equal(second.intro.hidden, true);
});

test("prompt is hidden when notifications are blocked and storage errors are visible", () => {
  const blocked = createPage({ permission: "denied" });
  assert.equal(blocked.intro.hidden, true);
  assert.equal(blocked.permissionRequests, 0);
  assert.match(blocked.status.textContent, /Allow them for this site in your browser's site settings/);
  const page = createPage({ storageError: true });
  page.introDismiss.listeners.click();
  assert.equal(page.intro.hidden, true);
  assert.match(page.status.textContent, /Could not save/);
});
