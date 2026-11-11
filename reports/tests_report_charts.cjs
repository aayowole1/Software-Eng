/* reports/tests_report_charts.cjs
 * Node tests for buildChartConfigs (SCRUM-37).
 * Run with: node --test reports/tests_report_charts.cjs
 */

"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { buildChartConfigs } = require("./static/reports/charts.js");

// ── Fixtures ──────────────────────────────────────────────────────────────────

const sampleData = {
  per_event: [
    { title: "General Body Meeting", rsvps_going: 4, attended: 4 },
    { title: "Workshop", rsvps_going: 10, attended: 7 },
  ],
  per_committee: [
    {
      name: "Finance",
      attendance_pct: 75,
      has_events: true,
      tasks_total: 10,
      tasks_completed: 3,
      tasks_overdue: 2,
    },
    {
      name: "Outreach",
      attendance_pct: 0,
      has_events: false,
      tasks_total: 5,
      tasks_completed: 5,
      tasks_overdue: 0,
    },
  ],
};

const emptyData = {
  per_event: [],
  per_committee: [],
};

// ── Tests ─────────────────────────────────────────────────────────────────────

test("returns null for null input", () => {
  assert.equal(buildChartConfigs(null, false), null);
});

test("returns null for empty per_event and per_committee", () => {
  assert.equal(buildChartConfigs(emptyData, false), null);
});

test("attendanceByEvent labels match per_event titles", () => {
  const configs = buildChartConfigs(sampleData, false);
  assert.ok(configs !== null);
  const labels = configs.attendanceByEvent.config.data.labels;
  assert.deepEqual(labels, ["General Body Meeting", "Workshop"]);
});

test("attendanceByEvent RSVPs Going dataset values match", () => {
  const configs = buildChartConfigs(sampleData, false);
  const rsvpDataset = configs.attendanceByEvent.config.data.datasets.find(
    (d) => d.label === "RSVPs Going"
  );
  assert.ok(rsvpDataset, "RSVPs Going dataset not found");
  assert.deepEqual(rsvpDataset.data, [4, 10]);
});

test("attendanceByEvent Attended dataset values match", () => {
  const configs = buildChartConfigs(sampleData, false);
  const attendedDataset = configs.attendanceByEvent.config.data.datasets.find(
    (d) => d.label === "Attended"
  );
  assert.ok(attendedDataset, "Attended dataset not found");
  assert.deepEqual(attendedDataset.data, [4, 7]);
});

test("attendanceByEvent aria-label contains first event title", () => {
  const configs = buildChartConfigs(sampleData, false);
  assert.ok(
    configs.attendanceByEvent.ariaLabel.includes("General Body Meeting"),
    `aria-label should mention first event: ${configs.attendanceByEvent.ariaLabel}`
  );
});

test("attendanceByCommittee labels match committee names", () => {
  const configs = buildChartConfigs(sampleData, false);
  const labels = configs.attendanceByCommittee.config.data.labels;
  assert.deepEqual(labels, ["Finance", "Outreach"]);
});

test("attendanceByCommittee attendance_pct is null for committees without events", () => {
  const configs = buildChartConfigs(sampleData, false);
  const pctData = configs.attendanceByCommittee.config.data.datasets[0].data;
  // Finance has events (index 0): value should be 75
  assert.equal(pctData[0], 75);
  // Outreach has no events (index 1): value should be null
  assert.equal(pctData[1], null);
});

test("tasksByCommittee Open = total − completed − overdue", () => {
  const configs = buildChartConfigs(sampleData, false);
  const datasets = configs.tasksByCommittee.config.data.datasets;
  const openDataset = datasets.find((d) => d.label === "Open");
  assert.ok(openDataset, "Open dataset not found");
  // Finance: 10 - 3 - 2 = 5
  assert.equal(openDataset.data[0], 5);
  // Outreach: 5 - 5 - 0 = 0
  assert.equal(openDataset.data[1], 0);
});

test("tasksByCommittee Completed dataset values match", () => {
  const configs = buildChartConfigs(sampleData, false);
  const datasets = configs.tasksByCommittee.config.data.datasets;
  const completedDataset = datasets.find((d) => d.label === "Completed");
  assert.ok(completedDataset, "Completed dataset not found");
  assert.deepEqual(completedDataset.data, [3, 5]);
});

test("tasksByCommittee Overdue dataset values match", () => {
  const configs = buildChartConfigs(sampleData, false);
  const datasets = configs.tasksByCommittee.config.data.datasets;
  const overdueDataset = datasets.find((d) => d.label === "Overdue");
  assert.ok(overdueDataset, "Overdue dataset not found");
  assert.deepEqual(overdueDataset.data, [2, 0]);
});

test("tasksByCommittee uses stacked bar chart", () => {
  const configs = buildChartConfigs(sampleData, false);
  const type = configs.tasksByCommittee.config.type;
  assert.equal(type, "bar");
  const xStacked = configs.tasksByCommittee.config.options.scales.x.stacked;
  const yStacked = configs.tasksByCommittee.config.options.scales.y.stacked;
  assert.ok(xStacked, "x axis should be stacked");
  assert.ok(yStacked, "y axis should be stacked");
});

test("prefersReducedMotion disables animation", () => {
  const configs = buildChartConfigs(sampleData, true);
  assert.equal(
    configs.attendanceByEvent.config.options.animation,
    false,
    "animation should be false when prefersReducedMotion is true"
  );
});

test("prefersReducedMotion false leaves animation undefined", () => {
  const configs = buildChartConfigs(sampleData, false);
  // animation key should not be explicitly set to false
  assert.notEqual(
    configs.attendanceByEvent.config.options.animation,
    false,
    "animation should not be false when prefersReducedMotion is false"
  );
});

test("only per_event data: attendanceByCommittee and tasksByCommittee are null", () => {
  const onlyEvents = { per_event: sampleData.per_event, per_committee: [] };
  const configs = buildChartConfigs(onlyEvents, false);
  assert.ok(configs !== null);
  assert.ok(configs.attendanceByEvent !== null);
  assert.equal(configs.attendanceByCommittee, null);
  assert.equal(configs.tasksByCommittee, null);
});

test("only per_committee data: attendanceByEvent is null", () => {
  const onlyCommittees = { per_event: [], per_committee: sampleData.per_committee };
  const configs = buildChartConfigs(onlyCommittees, false);
  assert.ok(configs !== null);
  assert.equal(configs.attendanceByEvent, null);
  assert.ok(configs.attendanceByCommittee !== null);
  assert.ok(configs.tasksByCommittee !== null);
});

test("Open count is clamped to 0 when overdue+completed exceed total", () => {
  const edgeData = {
    per_event: [],
    per_committee: [
      {
        name: "Edge",
        attendance_pct: null,
        has_events: false,
        tasks_total: 2,
        tasks_completed: 2,
        tasks_overdue: 1, // sum > total (data anomaly)
      },
    ],
  };
  const configs = buildChartConfigs(edgeData, false);
  const openDataset = configs.tasksByCommittee.config.data.datasets.find(
    (d) => d.label === "Open"
  );
  assert.ok(openDataset.data[0] >= 0, "Open should never be negative");
});
