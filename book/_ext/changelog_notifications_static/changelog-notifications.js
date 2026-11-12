(() => {
  "use strict";

  const script = document.currentScript;
  const manifestUrl = new URL("changelog-notifications.json", script.src);
  const bookUrl = new URL("../", script.src);
  const storageKey = `changelog-notifications:${bookUrl.href}`;
  const interval = 5 * 60 * 1000;

  const panel = document.createElement("div");
  panel.className = "changelog-notifications";
  const button = document.createElement("button");
  button.type = "button";
  const status = document.createElement("span");
  status.setAttribute("role", "status");
  panel.append(button, status);
  document.body.append(panel);

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
      button.textContent = "Changelog notifications unavailable";
      status.textContent = "A secure connection and a supported browser are required.";
      return;
    }
    try {
      const state = readState();
      button.disabled = false;
      button.textContent = state ? "Disable changelog notifications" : "Enable changelog notifications";
      status.textContent = state ? "Checks while this book is open." : "";
      if (Notification.permission === "denied") {
        status.textContent = "Notifications are blocked in your browser's site settings.";
      }
    } catch (error) {
      button.disabled = true;
      button.textContent = "Changelog notifications unavailable";
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
      if (!readState() || Notification.permission !== "granted") return;
      const manifest = await getManifest();
      const state = readState();
      if (!state || state.fingerprint === manifest.fingerprint || Notification.permission !== "granted") return;
      const notification = new Notification("Workbook changelog updated", {
        body: "Open the changelog to see what has changed.",
      });
      notification.onclick = () => {
        window.focus();
        window.location.href = new URL(manifest.url, bookUrl).href;
      };
      localStorage.setItem(storageKey, JSON.stringify({ fingerprint: manifest.fingerprint }));
      render();
    } catch (error) {
      status.textContent = "Could not check the changelog; will retry.";
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
    window.setInterval(check, interval);
  }
})();
