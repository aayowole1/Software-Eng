/* Dependency-free state checks. These do not replace a browser keyboard audit. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "static/core/sidebar.js"), "utf8");

function fixture(isMobile = true) {
  const documentEvents = {};
  const mediaEvents = {};
  const document = { activeElement: null, addEventListener: (name, callback) => { documentEvents[name] = callback; } };
  function element() {
    const events = {};
    const attributes = {};
    const classes = new Set();
    return {
      hidden: false, inert: false, attributes,
      classList: { toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name), contains: (name) => classes.has(name) },
      setAttribute: (name, value) => { attributes[name] = value; },
      addEventListener: (name, callback) => { events[name] = callback; },
      click: () => events.click(),
      focus() { document.activeElement = this; },
    };
  }
  const sidebar = element();
  const close = element();
  const open = element();
  const link = element();
  sidebar.contains = (node) => [sidebar, close, link].includes(node);
  sidebar.querySelector = () => link;
  document.getElementById = (id) => ({ sidebar, sidebarToggle: close, sidebarToggleMobile: open })[id];
  const media = { matches: isMobile, addEventListener: (name, callback) => { mediaEvents[name] = callback; } };
  vm.runInNewContext(source, { document, window: { matchMedia: () => media } });
  return {
    sidebar, close, open, link, document,
    escape() { let prevented = false; documentEvents.keydown({ key: "Escape", preventDefault() { prevented = true; } }); return prevented; },
    resize(isMobile) { media.matches = isMobile; mediaEvents.change(); },
  };
}

test("closed mobile navigation is hidden and inert with collapsed controls", () => {
  const ui = fixture();
  assert.equal(ui.sidebar.hidden, true);
  assert.equal(ui.sidebar.inert, true);
  assert.equal(ui.open.hidden, false);
  assert.equal(ui.close.hidden, true);
  assert.equal(ui.open.attributes["aria-expanded"], "false");
});

test("opening reveals navigation and moves focus to its close control", () => {
  const ui = fixture();
  ui.open.click();
  assert.equal(ui.sidebar.hidden, false);
  assert.equal(ui.sidebar.inert, false);
  assert.equal(ui.sidebar.classList.contains("open"), true);
  assert.equal(ui.open.attributes["aria-expanded"], "true");
  assert.equal(ui.document.activeElement, ui.close);
});

test("Escape closes mobile navigation and returns focus to the opener", () => {
  const ui = fixture();
  ui.open.click();
  ui.link.focus();
  assert.equal(ui.escape(), true);
  assert.equal(ui.sidebar.hidden, true);
  assert.equal(ui.sidebar.inert, true);
  assert.equal(ui.document.activeElement, ui.open);
});

test("close button restores focus without changing page navigation", () => {
  const ui = fixture();
  ui.open.click();
  ui.close.click();
  assert.equal(ui.sidebar.hidden, true);
  assert.equal(ui.document.activeElement, ui.open);
});

test("desktop navigation stays available and does not consume Escape", () => {
  const ui = fixture(false);
  assert.equal(ui.sidebar.hidden, false);
  assert.equal(ui.sidebar.inert, false);
  assert.equal(ui.open.hidden, true);
  assert.equal(ui.close.hidden, true);
  assert.equal(ui.open.attributes["aria-expanded"], "true");
  assert.equal(ui.escape(), false);
});

test("resize closes mobile navigation without leaving focus in a hidden panel", () => {
  const ui = fixture(false);
  ui.link.focus();
  ui.resize(true);
  assert.equal(ui.sidebar.hidden, true);
  assert.equal(ui.sidebar.inert, true);
  assert.equal(ui.document.activeElement, ui.open);
});

test("resize to desktop moves focus away from a now-hidden mobile opener", () => {
  const ui = fixture();
  ui.open.focus();
  ui.resize(false);
  assert.equal(ui.sidebar.hidden, false);
  assert.equal(ui.sidebar.inert, false);
  assert.equal(ui.document.activeElement, ui.link);
});
