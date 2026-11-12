(() => {
  "use strict";

  const script = document.currentScript;
  const manifestUrl = new URL("changelog-notifications.json", script.src);
  const bookUrl = new URL("../", script.src);
  const storageKey = `changelog-notifications:${bookUrl.href}`;
  const sessionKey = `${storageKey}:checked`;
  const introKey = `${storageKey}:intro-dismissed`;

  const panel = document.querySelector(".changelog-notifications");
  if (!panel) {
    console.error("Could not find the changelog notification button.");
    return;
  }
  const button = panel.querySelector("button");
  const status = panel.querySelector('[role="status"]');
  const intro = panel.querySelector(".changelog-notifications-intro");
  const introEnable = panel.querySelector("[data-changelog-enable]");
  const introDismiss = panel.querySelector("[data-changelog-dismiss]");

  function showIntro(show) {
    intro.hidden = !show;
    intro.classList.toggle("show", show);
  }

  function dismissIntro() {
    localStorage.setItem(introKey, "1");
    showIntro(false);
  }

  function setLabel(label) {
    button.setAttribute("aria-label", label);
    const tooltip = window.bootstrap?.Tooltip?.getInstance(button);
    if (tooltip) {
      button.setAttribute("data-bs-original-title", label);
      button.removeAttribute("title");
      tooltip.setContent({ ".tooltip-inner": label });
    } else {
      button.title = label;
    }
  }

  function setStatus(message) {
    status.textContent = message;
    status.parentElement.classList.toggle("show", Boolean(message));
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
      showIntro(false);
      button.disabled = true;
      setLabel("Changelog notifications unavailable");
      setIcon(false);
      setStatus("Notifications require a secure connection and a supported browser.");
      return;
    }
    try {
      const state = readState();
      showIntro(!state && !localStorage.getItem(introKey) && Notification.permission !== "denied");
      button.disabled = false;
      setLabel(state ? "Disable changelog notifications" : "Enable changelog notifications");
      button.setAttribute("aria-pressed", state ? "true" : "false");
      setIcon(Boolean(state));
      setStatus("");
      if (Notification.permission === "denied") {
        setStatus("Notifications are blocked in your browser's site settings.");
      }
    } catch (error) {
      showIntro(false);
      button.disabled = true;
      setLabel("Changelog notifications unavailable");
      setIcon(false);
      setStatus("Browser storage is unavailable.");
      console.error("Could not read changelog notification settings:", error);
    }
  }

  async function getManifest() {
    const response = await fetch(manifestUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`Changelog check failed: HTTP ${response.status}`);
    const manifest = await response.json();
    if (!/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/.test(manifest.fingerprint)
        || manifest.scheme !== "git-commit" || typeof manifest.url !== "string") {
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
      if (state.scheme === manifest.scheme && state.fingerprint !== manifest.fingerprint) {
        const notification = new Notification("Workbook changelog updated", {
          body: "Open the changelog to see what has changed.",
        });
        notification.onclick = () => {
          window.focus();
          window.location.href = new URL(manifest.url, bookUrl).href;
        };
      }
      localStorage.setItem(storageKey, JSON.stringify({
        fingerprint: manifest.fingerprint, scheme: manifest.scheme,
      }));
      sessionStorage.setItem(sessionKey, "1");
      render();
    } catch (error) {
      setStatus("Could not check the changelog; navigating to another page will retry.");
      console.error("Could not check changelog notifications:", error);
    }
  }

  async function toggleNotifications() {
    try {
      dismissIntro();
      if (readState()) {
        localStorage.removeItem(storageKey);
        render();
        return;
      }
      button.disabled = true;
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        render();
        if (permission !== "denied") setStatus("Notification permission was not granted.");
        return;
      }
      const manifest = await getManifest();
      sessionStorage.setItem(sessionKey, "1");
      localStorage.setItem(storageKey, JSON.stringify({
        fingerprint: manifest.fingerprint, scheme: manifest.scheme,
      }));
      render();
    } catch (error) {
      render();
      setStatus("Could not enable notifications; please try again.");
      console.error("Could not enable changelog notifications:", error);
    }
  }

  button.addEventListener("click", toggleNotifications);
  introEnable.addEventListener("click", toggleNotifications);
  introDismiss.addEventListener("click", () => {
    try {
      dismissIntro();
    } catch (error) {
      showIntro(false);
      setStatus("Could not save your preference in browser storage.");
      console.error("Could not dismiss changelog notifications prompt:", error);
    }
  });

  window.addEventListener("storage", (event) => {
    if (event.key === storageKey || event.key === introKey || event.key === null) render();
  });
  render();
  if (window.isSecureContext && "Notification" in window) {
    check();
  }
})();
