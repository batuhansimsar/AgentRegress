"""
AgentRegress — Regression Detector
Compares two repository snapshots and identifies introduced/fixed vulnerabilities.
"""

from __future__ import annotations
import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional

from regression.taxonomy import Vulnerability, VulnCategory, Severity, RegressionDistance
from regression.metrics import IterationSnapshot, RegressionEvent, MetricsCalculator, ExperimentResult


@dataclass
class SnapshotDiff:
    """
    The diff between two consecutive iteration snapshots.
    """
    iteration_from: int
    iteration_to: int
    fixed_vulns: list[Vulnerability]        # Present in t-1, absent in t
    introduced_vulns: list[Vulnerability]   # Absent in t-1, present in t
    persistent_vulns: list[Vulnerability]   # Present in both
    changed_files: list[str] = field(default_factory=list)
    regression_events: list[RegressionEvent] = field(default_factory=list)


class RegressionDetector:
    """
    Main detector that processes a sequence of iteration snapshots and
    produces a full regression analysis.
    """

    def __init__(self, experiment: ExperimentResult):
        self.experiment = experiment

    def run(self) -> ExperimentResult:
        """Run full regression detection pipeline."""
        calculator = MetricsCalculator(self.experiment)
        return calculator.compute_all()

    def get_diffs(self) -> list[SnapshotDiff]:
        """Return snapshot-to-snapshot diffs for all consecutive pairs."""
        diffs = []
        snaps = self.experiment.snapshots

        for i in range(1, len(snaps)):
            prev = snaps[i - 1]
            curr = snaps[i]
            diff = self._diff_snapshots(prev, curr)
            diffs.append(diff)

        return diffs

    def _diff_snapshots(self, prev: IterationSnapshot, curr: IterationSnapshot) -> SnapshotDiff:
        """Compare two consecutive snapshots."""
        prev_map = {self._vuln_key(v): v for v in prev.vulnerabilities}
        curr_map = {self._vuln_key(v): v for v in curr.vulnerabilities}

        prev_keys = set(prev_map.keys())
        curr_keys = set(curr_map.keys())

        fixed = [prev_map[k] for k in (prev_keys - curr_keys)]
        introduced = [curr_map[k] for k in (curr_keys - prev_keys)]
        persistent = [curr_map[k] for k in (curr_keys & prev_keys)]

        # Build regression events for new vulns
        events = []
        for vuln in introduced:
            fixed_cwe = fixed[0].cwe if fixed else None
            is_cross = False
            if fixed:
                is_cross = fixed[0].category != vuln.category

            distance = RegressionDistance.MODULE_LEVEL
            if curr.changed_files:
                from regression.taxonomy import classify_regression_distance
                changed_file = curr.changed_files[0]
                changed_module = changed_file.split("/")[0]
                vuln_module = vuln.file_path.split("/")[0]
                distance = classify_regression_distance(
                    changed_file, vuln.file_path, changed_module, vuln_module
                )

            events.append(RegressionEvent(
                introduced_vuln=vuln,
                iteration_from=prev.iteration,
                iteration_to=curr.iteration,
                distance=distance,
                is_cross_class=is_cross,
                is_migration=vuln.category == VulnCategory.VULNERABILITY_MIGRATION,
                fixed_vuln_cwe=fixed_cwe,
            ))

        return SnapshotDiff(
            iteration_from=prev.iteration,
            iteration_to=curr.iteration,
            fixed_vulns=fixed,
            introduced_vulns=introduced,
            persistent_vulns=persistent,
            changed_files=curr.changed_files,
            regression_events=events,
        )

    @staticmethod
    def _vuln_key(v: Vulnerability) -> str:
        """Create a stable key for a vulnerability (for deduplication)."""
        # Key on CWE + file path (not line number, as lines shift)
        return f"{v.cwe}::{v.file_path}"

    def vulnerability_graph(self) -> dict:
        """
        Build a directed graph: CWE-A (fixed) → CWE-B (introduced).
        Used for the 'which vulns lead to which' visualization.
        """
        edges: dict[str, dict[str, int]] = {}
        for diff in self.get_diffs():
            for event in diff.regression_events:
                if event.fixed_vuln_cwe and event.introduced_vuln:
                    src = event.fixed_vuln_cwe
                    dst = event.introduced_vuln.cwe
                    if src not in edges:
                        edges[src] = {}
                    edges[src][dst] = edges[src].get(dst, 0) + 1
        return edges

    def whack_a_mole_timeline(self) -> list[dict]:
        """
        Return a timeline suitable for the Whack-a-Mole dashboard visualization.
        Each entry = one iteration with: fixed, introduced, total.
        """
        timeline = []
        snaps = self.experiment.snapshots

        for i, snap in enumerate(snaps):
            entry = {
                "iteration": snap.iteration,
                "label": snap.label,
                "agent_action": snap.agent_action,
                "feedback": snap.feedback_received,
                "vulnerabilities": [v.to_dict() for v in snap.vulnerabilities],
                "total": len(snap.vulnerabilities),
                "severity_score": snap.severity_score,
            }
            if i > 0:
                prev = snaps[i - 1]
                prev_cwes = prev.vuln_ids
                curr_cwes = snap.vuln_ids
                entry["fixed"] = list(prev_cwes - curr_cwes)
                entry["introduced"] = list(curr_cwes - prev_cwes)
            else:
                entry["fixed"] = []
                entry["introduced"] = list(snap.vuln_ids)
            timeline.append(entry)

        return timeline

    def to_json(self) -> str:
        """Serialize the full regression analysis to JSON."""
        calculator = MetricsCalculator(self.experiment)
        result = calculator.compute_all()
        summary = calculator.summary()
        timeline = self.whack_a_mole_timeline()
        graph = self.vulnerability_graph()

        return json.dumps({
            "summary": summary,
            "timeline": timeline,
            "vulnerability_graph": graph,
            "regression_events": [
                {
                    "introduced": e.introduced_vuln.to_dict(),
                    "from_iteration": e.iteration_from,
                    "to_iteration": e.iteration_to,
                    "distance": e.distance.value if e.distance else None,
                    "is_cross_class": e.is_cross_class,
                    "is_migration": e.is_migration,
                    "fixed_cwe": e.fixed_vuln_cwe,
                }
                for e in result.regression_events
            ],
        }, indent=2)
