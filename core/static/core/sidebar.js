"use strict";

(() => {
  const sidebar = document.getElementById("sidebar");
  const closeButton = document.getElementById("sidebarToggle");
  const openButton = document.getElementById("sidebarToggleMobile");
  if (!sidebar || !closeButton || !openButton) return;
  const mobile = window.matchMedia("(max-width: 768px)");
  let open = false;

  function applyState() {
    const visible = !mobile.matches || open;
    sidebar.hidden = !visible;
    sidebar.inert = !visible;
    sidebar.classList.toggle("open", mobile.matches && open);
    openButton.hidden = !mobile.matches || open;
    closeButton.hidden = !mobile.matches || !open;
    for (const button of [openButton, closeButton]) {
      button.setAttribute("aria-expanded", String(visible));
    }
  }

  function closeNavigation() {
    open = false;
    applyState();
    if (mobile.matches) openButton.focus();
  }

  openButton.addEventListener("click", () => {
    if (!mobile.matches) return;
    open = true;
    applyState();
    closeButton.focus();
  });
  closeButton.addEventListener("click", closeNavigation);
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
    if (mobile.matches && focusedInside) {
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
