"use strict";

// Keep the delegation choices aligned with the selected committee. The server
// independently validates eligibility again when the form is submitted.
document.querySelectorAll("[data-assignment-form]").forEach((form) => {
  const committee = form.querySelector('[name="committee"]');
  const assignee = form.querySelector('[name="assignee"]');
  const feedback = form.querySelector("[data-assignment-feedback]");
  const retry = form.querySelector("[data-assignment-retry]");
  if (!committee || !assignee || !feedback || !retry) return;

  const submitButtons = [...form.querySelectorAll('button[type="submit"], input[type="submit"]')];
  const initiallyDisabled = new Map(submitButtons.map((button) => [button, button.disabled]));
  let requestNumber = 0;
  let controller;
  let pending = false;
  let failed = false;

  function updateControls() {
    assignee.disabled = pending || failed;
    assignee.setAttribute("aria-busy", String(pending));
    retry.hidden = !failed;
    retry.style.display = failed ? "" : "none";
    submitButtons.forEach((button) => {
      button.disabled = initiallyDisabled.get(button) || pending || failed;
    });
  }

  async function refreshAssignees() {
    const number = ++requestNumber;
    if (controller) controller.abort();
    controller = new AbortController();
    const previousValue = assignee.value;
    pending = true;
    failed = false;
    feedback.textContent = "Loading eligible members…";
    updateControls();

    try {
      const url = new URL(form.dataset.assigneesUrl, window.location.href);
      if (url.origin !== window.location.origin) throw new Error("Unexpected origin");
      url.searchParams.set("committee", committee.value);
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal: controller.signal,
        cache: "no-store",
      });
      if (!response.ok || response.redirected) throw new Error("Members unavailable");
      const data = await response.json();
      if (!Array.isArray(data.assignees)) throw new Error("Invalid member list");
      if (number !== requestNumber) return;

      const options = [new Option("Unassigned", "")];
      let preserved = false;
      data.assignees.forEach((member) => {
        if (typeof member.id !== "string" || typeof member.label !== "string") {
          throw new Error("Invalid member choice");
        }
        const selected = member.id === previousValue;
        preserved = preserved || selected;
        options.push(new Option(member.label, member.id, false, selected));
      });
      assignee.replaceChildren(...options);
      if (!preserved) assignee.value = "";
      feedback.textContent = previousValue && !preserved
        ? "The previous assignee is not eligible for this committee. Choose a member or leave the task unassigned."
        : `${data.assignees.length} eligible member${data.assignees.length === 1 ? "" : "s"} available.`;
    } catch {
      if (number !== requestNumber) return;
      failed = true;
      feedback.textContent = "Could not load eligible members. Retry the member list before saving.";
    } finally {
      if (number === requestNumber) {
        pending = false;
        updateControls();
      }
    }
  }

  committee.addEventListener("change", refreshAssignees);
  retry.addEventListener("click", refreshAssignees);
  form.addEventListener("submit", (event) => {
    if (pending || failed) {
      event.preventDefault();
      feedback.textContent = pending
        ? "Wait for the eligible member list to finish loading before saving."
        : "Retry the member list before saving.";
    }
  });
});
