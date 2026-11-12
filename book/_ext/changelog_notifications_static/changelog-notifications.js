(() => {
  "use strict";

  const script = document.currentScript;
  const manifestUrl = new URL("changelog-notifications.json", script.src);
  const bookUrl = new URL("../", script.src);
  const storageKey = `changelog-notifications:${bookUrl.href}`;
  const sessionKey = `${storageKey}:checked`;
  const visitedKey = `${storageKey}:visited`;
  const permissionKey = `${storageKey}:permission`;
  const introKey = `${storageKey}:intro-dismissed`;

  const panel = document.querySelector(".changelog-notifications");
  if (!panel) {
    console.error("Could not find the changelog notification button.");
    return;
  }
  const button = panel.querySelector("button");
  const menu = panel.querySelector(".changelog-notifications-menu");
  const status = panel.querySelector('[role="status"]');
  const statusContainer = panel.querySelector(".changelog-notifications-status");
  const statusClose = panel.querySelector("[data-changelog-status-close]");
  const intro = panel.querySelector(".changelog-notifications-intro");
  const toggleButton = panel.querySelector("[data-changelog-toggle]");
  const toggleIcon = panel.querySelector("[data-changelog-toggle-icon]");
  const toggleLabel = panel.querySelector("[data-changelog-toggle-label]");
  const introDismiss = panel.querySelector("[data-changelog-dismiss]");

  function showMenu(show) {
    menu.classList.toggle("show", show);
    panel.classList.toggle("show", show);
    if (show) panel.classList.remove("hover-dismissed");
    else if (panel.matches(":hover")) panel.classList.add("hover-dismissed");
    const expanded = show || (panel.matches(":hover") && !panel.classList.contains("hover-dismissed"));
    button.setAttribute("aria-expanded", expanded ? "true" : "false");
  }

  function showIntro(show) {
    intro.hidden = !show;
  }

  function dismissIntro() {
    localStorage.setItem(introKey, "1");
    showIntro(false);
    showMenu(false);
  }

  function setLabel(label) {
    button.setAttribute("aria-label", label);
  }

  function setStatus(message, dismissible = false) {
    status.textContent = message;
    statusContainer.hidden = !message;
    statusClose.hidden = !message || !dismissible;
  }

  function setIcon(target, enabled) {
    const icon = document.createElement("i");
    icon.setAttribute("aria-hidden", "true");
    icon.className = enabled ? "fa-solid fa-bell" : "fa-solid fa-bell-slash";
    target.replaceChildren(icon);
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

  function render({ initial = false, showBlocked = false } = {}) {
    if (!window.isSecureContext || !("Notification" in window)) {
      showIntro(false);
      button.disabled = true;
      setLabel("Changelog notifications unavailable");
      setIcon(button, false);
      setStatus("Notifications require a secure connection and a supported browser.");
      showMenu(true);
      return;
    }
    try {
      const previousPermission = sessionStorage.getItem(permissionKey);
      sessionStorage.setItem(permissionKey, Notification.permission);
      if (initial) {
        showBlocked = !sessionStorage.getItem(visitedKey);
        sessionStorage.setItem(visitedKey, "1");
      }
      const state = readState();
      const permissionGranted = initial && previousPermission && previousPermission !== "granted"
        && Notification.permission === "granted" && !state;
      const showPrompt = !permissionGranted && !state && !localStorage.getItem(introKey)
        && Notification.permission !== "denied";
      showIntro(showPrompt);
      button.disabled = false;
      toggleButton.disabled = false;
      setLabel("Changelog notification settings");
      toggleLabel.textContent = state ? "Disable notifications" : "Enable notifications";
      toggleButton.setAttribute("aria-pressed", state ? "true" : "false");
      setIcon(button, Boolean(state));
      setIcon(toggleIcon, Boolean(state));
      setStatus("");
      if (showBlocked && Notification.permission === "denied") {
        setStatus("Notifications are blocked. Allow them for this site in your browser's site settings (usually via the icon next to the address bar), then use the bell if notifications are not enabled.", true);
      } else if (permissionGranted) {
        setStatus("Browser permission is allowed. Select Enable notifications below to turn on changelog notifications.", true);
      }
      if (initial && (showPrompt || permissionGranted || (showBlocked && Notification.permission === "denied"))) {
        showMenu(true);
      }
    } catch (error) {
      showIntro(false);
      button.disabled = true;
      toggleButton.disabled = true;
      setLabel("Changelog notifications unavailable");
      setIcon(button, false);
      setIcon(toggleIcon, false);
      setStatus("Browser storage is unavailable.");
      showMenu(true);
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

  // The first page of a tab session may notify; later pages only refresh the
  // stored commit, since the reader is already seeing the current content.
  async function check() {
    const alreadyChecked = Boolean(sessionStorage.getItem(sessionKey));
    try {
      if (!readState() || Notification.permission !== "granted") return;
      const manifest = await getManifest();
      const state = readState();
      if (!state || Notification.permission !== "granted") return;
      if (!alreadyChecked && state.scheme === manifest.scheme && state.fingerprint !== manifest.fingerprint) {
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
      if (alreadyChecked) return;
      setStatus("Could not check the changelog; navigating to another page will retry.");
      showMenu(true);
      console.error("Could not check changelog notifications:", error);
    }
  }

  async function toggleNotifications() {
    try {
      if (readState()) {
        localStorage.removeItem(storageKey);
        render();
        return;
      }
      localStorage.setItem(introKey, "1");
      showIntro(false);
      toggleButton.disabled = true;
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        render({ showBlocked: true });
        showMenu(true);
        if (permission !== "denied") {
          setStatus("Notification permission was not granted. Try the bell again. If no prompt appears, check your browser's site settings, usually via the icon next to the address bar.");
        }
        return;
      }
      const manifest = await getManifest();
      sessionStorage.setItem(sessionKey, "1");
      localStorage.setItem(storageKey, JSON.stringify({
        fingerprint: manifest.fingerprint, scheme: manifest.scheme,
      }));
      render();
      showMenu(true);
    } catch (error) {
      render();
      setStatus("Could not enable notifications; please try again.");
      showMenu(true);
      console.error("Could not enable changelog notifications:", error);
    }
  }

  button.addEventListener("shown.bs.dropdown", () => {
    panel.classList.remove("hover-dismissed");
    button.setAttribute("aria-expanded", "true");
  });
  button.addEventListener("hide.bs.dropdown", () => {
    if (panel.matches(":hover")) panel.classList.add("hover-dismissed");
  });
  panel.addEventListener("mouseenter", () => {
    if (!panel.classList.contains("hover-dismissed")) {
      button.setAttribute("aria-expanded", "true");
    }
  });
  panel.addEventListener("mouseleave", () => {
    panel.classList.remove("hover-dismissed");
    button.setAttribute("aria-expanded", menu.classList.contains("show") ? "true" : "false");
  });
  toggleButton.addEventListener("click", toggleNotifications);
  statusClose.addEventListener("click", () => {
    setStatus("");
    if (!intro.hidden) return;
    showMenu(false);
    button.focus();
  });
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
  render({ initial: true });
  if (window.isSecureContext && "Notification" in window) {
    check();
  }
})();
