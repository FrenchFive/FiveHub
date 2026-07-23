// Report window — the pass/fail breakdown of one publish validation.

const box = document.getElementById("report");
const { path: reportPath } = queryParams();

function ruleBlock(result) {
  const node = el("div", "rule " + result.status);
  node.appendChild(el("div", "status", result.status.toUpperCase()));

  const body = el("div", "body");
  body.appendChild(el("div", "rule-label", result.label));
  if (result.messages.length) {
    const messages = el("div", "messages");
    for (const message of result.messages) {
      messages.appendChild(el("div", null, "— " + message));
    }
    body.appendChild(messages);
  }
  node.appendChild(body);

  node.appendChild(
    el("div", "sev", result.status === "fail" ? result.severity : result.rule_id),
  );
  return node;
}

async function load() {
  try {
    const { report, path } = await window.fivehub.report(reportPath);
    document.title = "FIVEHUB — " + report.asset_name + " VALIDATION";
    document.getElementById("report-path").textContent = path;

    clear(box);

    const verdict = el(
      "div",
      "verdict" + (report.passed ? "" : " failed"),
      report.passed ? "PASSED" : "FAILED",
    );
    box.appendChild(verdict);

    const meta = el("div", "row");
    meta.appendChild(el("span", "label", report.asset_name));
    meta.appendChild(el("span", "label", "VARIANT: " + report.variant));
    meta.appendChild(el("span", "spacer"));
    meta.appendChild(
      el("span", "label", report.error_count + " ERRORS · " + report.warning_count + " WARNINGS"),
    );
    box.appendChild(meta);

    const list = el("div");
    list.style.borderTop = "1px solid #fff";
    for (const result of report.results) list.appendChild(ruleBlock(result));
    box.appendChild(list);
  } catch (error) {
    showError(box, error);
  }
}

load();
