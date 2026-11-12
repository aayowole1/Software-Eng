"use strict";

(() => {
  const sidebar = document.getElementById("sidebar");
  const closeButton = document.getElementById("sidebarToggle");
  const openButton = document.getElementById("sidebarToggleMobile");
  const collapseButton = document.getElementById("sidebarCollapseToggle");
  if (!sidebar) return;
  const mobile = window.matchMedia("(max-width: 768px)");
  let open = false;
  let collapsed = false;

  try {
    collapsed = window.localStorage.getItem("orgflow.sidebar.collapsed") === "true";
  } catch (error) {
    // Keep collapse usable when browser storage is unavailable.
  }

  function applyState() {
    const visible = !mobile.matches || open;
    sidebar.hidden = !visible;
    sidebar.inert = !visible;
    sidebar.classList.toggle("open", mobile.matches && open);
    sidebar.classList.toggle("collapsed", !mobile.matches && collapsed);
    if (openButton) openButton.hidden = !mobile.matches || open;
    if (closeButton) closeButton.hidden = !mobile.matches || !open;
    if (collapseButton) {
      collapseButton.hidden = mobile.matches;
      collapseButton.setAttribute("aria-expanded", String(!collapsed));
      collapseButton.setAttribute(
        "aria-label",
        collapsed ? "Expand navigation" : "Collapse navigation",
      );
    }
    for (const button of [openButton, closeButton].filter(Boolean)) {
      button.setAttribute("aria-expanded", String(visible));
    }
  }

  function closeNavigation() {
    open = false;
    applyState();
    if (mobile.matches && openButton) openButton.focus();
  }

  openButton?.addEventListener("click", () => {
    if (!mobile.matches) return;
    open = true;
    applyState();
    closeButton?.focus();
  });
  closeButton?.addEventListener("click", closeNavigation);
  collapseButton?.addEventListener("click", () => {
    collapsed = !collapsed;
    try {
      window.localStorage.setItem("orgflow.sidebar.collapsed", String(collapsed));
    } catch (error) {
      // The current page state still applies without persistence.
    }
    applyState();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && mobile.matches && open) {
      event.preventDefault();
      closeNavigation();
    }
  });

  function resizeNavigation() {
    const focusedInside = sidebar.contains(document.activeElement);
    const focusedToggle = [openButton, closeButton].includes(document.activeElement);
    open = false;
    applyState();
    if (mobile.matches && focusedInside && openButton) {
      openButton.focus();
    } else if (!mobile.matches && focusedToggle) {
      sidebar.querySelector("a[href]")?.focus();
    }
  }
  if (mobile.addEventListener) {
    mobile.addEventListener("change", resizeNavigation);
  } else {
    mobile.addListener(resizeNavigation);
  }
  applyState();
})();
