/* reports/static/reports/charts.js
 * Interactive charts for the officer Reports page (SCRUM-37).
 * Requires Chart.js 4.6.1 (vendor/chart.umd.min.js), loaded before this file.
 * This file is loaded with defer and uses no browser globals at the module level
 * so that buildChartConfigs can be tested with Node.
 */

"use strict";

/**
 * Build Chart.js config objects from report data.
 *
 * @param {Object} data - Parsed JSON from the page (chart_data script tag).
 *   data.per_event: Array<{title, rsvps_going, attended}>
 *   data.per_committee: Array<{name, attendance_pct, tasks_total,
 *                              tasks_completed, tasks_overdue, has_events}>
 * @param {boolean} prefersReducedMotion - Disable animations when true.
 * @returns {{ attendanceByEvent, attendanceByCommittee, tasksByCommittee }|null}
 *   null when there is no data to show.
 */
function buildChartConfigs(data, prefersReducedMotion) {
  if (!data) return null;

  const hasEvents = data.per_event && data.per_event.length > 0;
  const hasCommittees = data.per_committee && data.per_committee.length > 0;
  if (!hasEvents && !hasCommittees) return null;

  const animationOff = prefersReducedMotion
    ? { animation: false, transitions: { active: { animation: { duration: 0 } } } }
    : {};

  /* ── 1. Attendance by event ── */
  let attendanceByEvent = null;
  if (hasEvents) {
    const eventLabels = data.per_event.map((e) => e.title);
    const rsvpData = data.per_event.map((e) => e.rsvps_going);
    const attendedData = data.per_event.map((e) => e.attended);

    // Build aria-label: list first event's numbers as a sample summary.
    const firstEvent = data.per_event[0];
    const ariaLabel =
      `Attendance by event: ${firstEvent.title} ` +
      `${firstEvent.attended} attended of ${firstEvent.rsvps_going} RSVPs`;

    attendanceByEvent = {
      ariaLabel,
      config: {
        type: "bar",
        data: {
          labels: eventLabels,
          datasets: [
            {
              label: "RSVPs Going",
              data: rsvpData,
              // Blue, ≥ 3:1 on white (#ffffff): #1a56cc passes (4.56:1)
              backgroundColor: "#1a56cc",
            },
            {
              label: "Attended",
              // Green, ≥ 3:1 on white: #1c7a40 passes (4.68:1)
              backgroundColor: "#1c7a40",
              data: attendedData,
            },
          ],
        },
        options: {
          ...animationOff,
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            legend: { position: "top" },
            tooltip: { mode: "index", intersect: false },
          },
          scales: {
            x: { title: { display: true, text: "Event" } },
            y: { beginAtZero: true, title: { display: true, text: "Count" } },
          },
        },
      },
    };
  }

  /* ── 2. Attendance % by committee ── */
  let attendanceByCommittee = null;
  if (hasCommittees) {
    const labels = data.per_committee.map((c) => c.name);
    const pctData = data.per_committee.map((c) =>
      c.has_events ? c.attendance_pct : null
    );

    // Build aria-label from first committee that has a value.
    const first = data.per_committee.find((c) => c.has_events);
    const ariaLabel = first
      ? `Attendance by committee: ${first.name} ${first.attendance_pct}%`
      : "Attendance by committee: no events in range";

    attendanceByCommittee = {
      ariaLabel,
      labels, // kept for the "No events" annotation
      hasEventsFlags: data.per_committee.map((c) => c.has_events),
      config: {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              label: "Attendance %",
              data: pctData,
              backgroundColor: "#c46200", // Orange-brown, 4.84:1 on white
            },
          ],
        },
        options: {
          ...animationOff,
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            legend: { position: "top" },
            tooltip: {
              callbacks: {
                label: (ctx) => {
                  const idx = ctx.dataIndex;
                  if (!data.per_committee[idx].has_events) return "No events";
                  return `Attendance: ${ctx.parsed.y}%`;
                },
              },
            },
          },
          scales: {
            x: { title: { display: true, text: "Committee" } },
            y: {
              beginAtZero: true,
              max: 100,
              title: { display: true, text: "Attendance %" },
            },
          },
        },
      },
    };
  }

  /* ── 3. Tasks by committee (stacked) ── */
  let tasksByCommittee = null;
  if (hasCommittees) {
    const labels = data.per_committee.map((c) => c.name);
    const completed = data.per_committee.map((c) => c.tasks_completed);
    const overdue = data.per_committee.map((c) => c.tasks_overdue);
    const open = data.per_committee.map(
      (c) => Math.max(0, c.tasks_total - c.tasks_completed - c.tasks_overdue)
    );

    const firstC = data.per_committee[0];
    const ariaLabel =
      `Tasks by committee: ${firstC.name} ` +
      `${firstC.tasks_completed} completed, ` +
      `${Math.max(0, firstC.tasks_total - firstC.tasks_completed - firstC.tasks_overdue)} open, ` +
      `${firstC.tasks_overdue} overdue`;

    tasksByCommittee = {
      ariaLabel,
      config: {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              label: "Completed",
              data: completed,
              backgroundColor: "#1c7a40", // Green 4.68:1
              stack: "tasks",
            },
            {
              label: "Open",
              data: open,
              backgroundColor: "#1a56cc", // Blue 4.56:1
              stack: "tasks",
            },
            {
              label: "Overdue",
              data: overdue,
              backgroundColor: "#b42318", // Red 5.14:1
              stack: "tasks",
            },
          ],
        },
        options: {
          ...animationOff,
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            legend: { position: "top" },
            tooltip: { mode: "index", intersect: false },
          },
          scales: {
            x: {
              stacked: true,
              title: { display: true, text: "Committee" },
            },
            y: {
              stacked: true,
              beginAtZero: true,
              title: { display: true, text: "Tasks" },
            },
          },
        },
      },
    };
  }

  return { attendanceByEvent, attendanceByCommittee, tasksByCommittee };
}

/* ── Browser initialisation (skipped when loaded with Node's require()) ── */
if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    const scriptTag = document.getElementById("chart-data");
    if (!scriptTag) return;

    let data;
    try {
      data = JSON.parse(scriptTag.textContent);
    } catch (_) {
      return;
    }

    const prefersReducedMotion =
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const configs = buildChartConfigs(data, prefersReducedMotion);

    // Show the no-data message when there is nothing to chart.
    if (!configs) {
      const msg = document.getElementById("charts-no-data");
      if (msg) msg.hidden = false;
      return;
    }

    function renderChart(canvasId, cfg) {
      if (!cfg) return;
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      canvas.setAttribute("aria-label", cfg.ariaLabel);
      new Chart(canvas, cfg.config); // eslint-disable-line no-undef
    }

    renderChart("chart-attendance-event", configs.attendanceByEvent);

    // For the committee attendance chart, draw "No events" text annotations
    // over null bars using an afterDraw plugin.
    if (configs.attendanceByCommittee) {
      const ac = configs.attendanceByCommittee;
      const canvas = document.getElementById("chart-attendance-committee");
      if (canvas) {
        canvas.setAttribute("aria-label", ac.ariaLabel);
        const noEventsPlugin = {
          id: "noEventsLabel",
          afterDraw(chart) {
            const ctx = chart.ctx;
            const meta = chart.getDatasetMeta(0);
            ac.hasEventsFlags.forEach((hasEvents, i) => {
              if (!hasEvents) {
                const bar = meta.data[i];
                if (!bar) return;
                ctx.save();
                ctx.fillStyle = "#5f5f5a";
                ctx.font = "11px system-ui, sans-serif";
                ctx.textAlign = "center";
                ctx.fillText("No events", bar.x, bar.y - 6);
                ctx.restore();
              }
            });
          },
        };
        new Chart(canvas, { // eslint-disable-line no-undef
          ...ac.config,
          plugins: [noEventsPlugin],
        });
      }
    }

    renderChart("chart-tasks-committee", configs.tasksByCommittee);
  });
}

/* Export for Node tests */
if (typeof module !== "undefined") {
  module.exports = { buildChartConfigs };
}
