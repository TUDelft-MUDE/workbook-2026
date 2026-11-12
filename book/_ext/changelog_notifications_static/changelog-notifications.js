(() => {
  "use strict";

  const script = document.currentScript;
  const manifestUrl = new URL("changelog-notifications.json", script.src);
  const bookUrl = new URL("../", script.src);
  const storageKey = `changelog-notifications:${bookUrl.href}`;
  const sessionKey = `${storageKey}:checked`;

  const toolbar = document.querySelector(".article-header-buttons");
  if (!toolbar) {
    console.error("Could not find the workbook's article header buttons.");
    return;
  }
  const panel = document.createElement("div");
  panel.className = "changelog-notifications";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn btn-sm";
  const status = document.createElement("span");
  status.setAttribute("role", "status");
  panel.append(button, status);
  toolbar.append(panel);

  function setLabel(label) {
    button.title = label;
    button.setAttribute("aria-label", label);
  }

  function setIcon(enabled) {
    const icon = document.createElement("i");
    icon.setAttribute("aria-hidden", "true");
    icon.className = enabled ? "fa-solid fa-bell" : "fa-solid fa-bell-slash";
    button.replaceChildren(icon);
  }

  function readState() {
    const value = localStorage.getItem(storageKey);
    if (!value) return null;
    const state = JSON.parse(value);
    if (typeof state.fingerprint !== "string") {
      throw new Error("Invalid notification settings");
    }
    return state;
  }

  function render() {
    if (!window.isSecureContext || !("Notification" in window)) {
      button.disabled = true;
      setLabel("Changelog notifications unavailable");
      setIcon(false);
      status.textContent = "Notifications require a secure connection and a supported browser.";
      return;
    }
    try {
      const state = readState();
      button.disabled = false;
      setLabel(state ? "Disable changelog notifications" : "Enable changelog notifications");
      button.setAttribute("aria-pressed", state ? "true" : "false");
      setIcon(Boolean(state));
      status.textContent = "";
      if (Notification.permission === "denied") {
        status.textContent = "Notifications are blocked in your browser's site settings.";
      }
    } catch (error) {
      button.disabled = true;
      setLabel("Changelog notifications unavailable");
      setIcon(false);
      status.textContent = "Browser storage is unavailable.";
      console.error("Could not read changelog notification settings:", error);
    }
  }

  async function getManifest() {
    const response = await fetch(manifestUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`Changelog check failed: HTTP ${response.status}`);
    const manifest = await response.json();
    if (!/^[a-f0-9]{64}$/.test(manifest.fingerprint) || typeof manifest.url !== "string") {
      throw new Error("Invalid changelog fingerprint");
    }
    return manifest;
  }

  async function check() {
    try {
      if (!readState() || Notification.permission !== "granted" || sessionStorage.getItem(sessionKey)) return;
      const manifest = await getManifest();
      const state = readState();
      if (!state || Notification.permission !== "granted") return;
      if (state.fingerprint !== manifest.fingerprint) {
        const notification = new Notification("Workbook changelog updated", {
          body: "Open the changelog to see what has changed.",
        });
        notification.onclick = () => {
          window.focus();
          window.location.href = new URL(manifest.url, bookUrl).href;
        };
        localStorage.setItem(storageKey, JSON.stringify({ fingerprint: manifest.fingerprint }));
      }
      sessionStorage.setItem(sessionKey, "1");
      render();
    } catch (error) {
      status.textContent = "Could not check the changelog; navigating to another page will retry.";
      console.error("Could not check changelog notifications:", error);
    }
  }

  button.addEventListener("click", async () => {
    try {
      if (readState()) {
        localStorage.removeItem(storageKey);
        render();
        return;
      }
      button.disabled = true;
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        render();
        if (permission !== "denied") status.textContent = "Notification permission was not granted.";
        return;
      }
      const manifest = await getManifest();
      sessionStorage.setItem(sessionKey, "1");
      localStorage.setItem(storageKey, JSON.stringify({ fingerprint: manifest.fingerprint }));
      render();
    } catch (error) {
      render();
      status.textContent = "Could not enable notifications; please try again.";
      console.error("Could not enable changelog notifications:", error);
    }
  });

  window.addEventListener("storage", (event) => {
    if (event.key === storageKey || event.key === null) render();
  });
  render();
  if (window.isSecureContext && "Notification" in window) {
    check();
  }
})();
