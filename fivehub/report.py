"""Validation framework: rules, results and the pass/fail report.

A rule returns a list of issue messages — empty means PASS. ERROR severity
failures block the publish; WARNING failures are recorded but let it through.
The report serializes to JSON (stored with the publish, rendered by the app)
and to plain text (shown inside the DCC).
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone


class Severity:
    ERROR = "error"
    WARNING = "warning"


class Status:
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Rule:
    """Base validation rule. Subclasses set ``rule_id``/``label``/``severity``
    and implement ``check(request) -> list[str]`` returning issue messages."""

    rule_id = "rule"
    label = "Rule"
    severity = Severity.ERROR

    def __init__(self, **params):
        # Allow per-publish overrides, e.g. severity="warning" or tolerances.
        for key, value in params.items():
            setattr(self, key, value)

    def check(self, request):
        raise NotImplementedError

    def applies(self, request):
        return True


@dataclass
class RuleResult:
    rule_id: str
    label: str
    severity: str
    status: str
    messages: list = field(default_factory=list)

    def to_dict(self):
        return {
            "rule_id": self.rule_id,
            "label": self.label,
            "severity": self.severity,
            "status": self.status,
            "messages": list(self.messages),
        }


@dataclass
class ValidationReport:
    asset_name: str
    variant: str = "default"
    project: str = ""
    created_at: str = field(default_factory=utc_now)
    results: list = field(default_factory=list)

    @property
    def passed(self):
        return not any(
            r.status == Status.FAIL and r.severity == Severity.ERROR for r in self.results
        )

    @property
    def error_count(self):
        return sum(
            1 for r in self.results if r.status == Status.FAIL and r.severity == Severity.ERROR
        )

    @property
    def warning_count(self):
        return sum(
            1 for r in self.results if r.status == Status.FAIL and r.severity == Severity.WARNING
        )

    def to_dict(self):
        return {
            "asset_name": self.asset_name,
            "variant": self.variant,
            "project": self.project,
            "created_at": self.created_at,
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "results": [r.to_dict() for r in self.results],
        }

    @classmethod
    def from_dict(cls, data):
        report = cls(
            asset_name=data.get("asset_name", ""),
            variant=data.get("variant", "default"),
            project=data.get("project", ""),
            created_at=data.get("created_at", ""),
        )
        for entry in data.get("results", []):
            report.results.append(
                RuleResult(
                    rule_id=entry.get("rule_id", ""),
                    label=entry.get("label", ""),
                    severity=entry.get("severity", Severity.ERROR),
                    status=entry.get("status", Status.SKIP),
                    messages=list(entry.get("messages", [])),
                )
            )
        return report

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2)
        return path

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    def to_text(self):
        """Plain-text rendering for DCC dialogs and terminals."""
        lines = []
        verdict = "PASSED" if self.passed else "FAILED"
        lines.append("VALIDATION %s — %s (variant: %s)" % (verdict, self.asset_name, self.variant))
        lines.append("%d error(s), %d warning(s)" % (self.error_count, self.warning_count))
        lines.append("-" * 60)
        for result in self.results:
            mark = {Status.PASS: "PASS", Status.FAIL: "FAIL", Status.SKIP: "SKIP"}[result.status]
            severity = " (%s)" % result.severity if result.status == Status.FAIL else ""
            lines.append("[%s] %s%s" % (mark, result.label, severity))
            for message in result.messages:
                lines.append("       - %s" % message)
        return "\n".join(lines)


def run_rules(rules, request):
    """Run every rule against the request and assemble the report."""
    report = ValidationReport(
        asset_name=request.asset_name,
        variant=request.variant,
        project=request.project,
    )
    for rule in rules:
        if not rule.applies(request):
            report.results.append(
                RuleResult(rule.rule_id, rule.label, rule.severity, Status.SKIP)
            )
            continue
        messages = rule.check(request)
        status = Status.FAIL if messages else Status.PASS
        report.results.append(
            RuleResult(rule.rule_id, rule.label, rule.severity, status, list(messages))
        )
    return report
