/* Browser-facing contract checks for the notes recording flow.
 * These run without a server or provider and catch regressions in the
 * rendered controls and submit state machine.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const source = fs.readFileSync(
  path.join(__dirname, "templates", "meetings", "draft_form.html"),
  "utf8",
);

function position(text) {
  const index = source.indexOf(text);
  assert.notEqual(index, -1, `Missing browser flow marker: ${text}`);
  return index;
}

test("creation page exposes microphone recording controls", () => {
  assert.match(source, /id="start-recording"/);
  assert.match(source, /id="stop-recording"/);
  assert.match(source, /navigator\.mediaDevices\.getUserMedia\(\{ audio: true \}\)/);
  assert.match(source, /X-Recording-Final/);
});

test("submit immediately replaces the creation view with processing state", () => {
  assert.match(source, /function showProcessingPage\(\)/);
  assert.match(source, /main\.replaceChildren\(processingCard, form\)/);
  assert.ok(position("showProcessingPage();") < position("finalizeRecording().then"));
  assert.match(source, /Submitting notes and preparing the draft/);
});

test("pause and resume remain separate from final submission", () => {
  assert.match(source, /async function stopRecording\(forSubmission = false\)/);
  assert.match(source, /if \(!forSubmission\) \{/);
  assert.match(source, /status\.textContent = "Notes paused\."/);
  assert.match(source, /async function finalizeRecording\(\)/);
  assert.match(source, /if \(isRecording\) await stopRecording\(true\)/);
  assert.match(source, /stream\.getTracks\(\)\.forEach/);
});
