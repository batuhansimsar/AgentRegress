from agents.base_agent import FeedbackMode, Task
from agents.prompt_builder import PromptBuilder
from regression.metrics import ExperimentResult, IterationSnapshot, MetricsCalculator
from regression.taxonomy import Severity, Vulnerability, VulnCategory


def vulnerability(identifier, cwe, file_path, snippet):
    return Vulnerability(
        id=identifier, cwe=cwe, name=cwe, category=VulnCategory.INJECTION,
        severity=Severity.HIGH, file_path=file_path, snippet=snippet,
    )


def test_metrics_tracks_two_instances_of_the_same_cwe_independently():
    original = vulnerability("one", "CWE-89", "app.py", "query_a")
    introduced = vulnerability("two", "CWE-89", "app.py", "query_b")
    result = ExperimentResult(
        experiment_id="x", agent_name="test", task_id="T", task_type="type_a",
        task_description="x",
        snapshots=[
            IterationSnapshot(0, "t0", [original], build_passed=True, functional_tests_passed=True, security_tests_passed=False),
            IterationSnapshot(1, "t1", [introduced], build_passed=True, functional_tests_passed=True, security_tests_passed=True),
        ],
        task_solved=True,
    )
    MetricsCalculator(result).compute_all()
    assert result.total_fixed == 1
    assert result.total_introduced == 1
    assert result.regression_events[0].introduced_vuln.fingerprint == introduced.fingerprint


def test_prompt_treatments_are_experimentally_distinct():
    task = Task("T", "type_b", "repair", "/tmp", ["f"], ["s"], source_files=["app.py"])
    common = dict(task=task, iteration=1, functional_feedback="functional", build_feedback="build",
                  security_feedback="security", scanner_feedback="scanner", source_context="source")
    baseline = PromptBuilder.build(feedback_mode=FeedbackMode.BASELINE, **common)
    aware = PromptBuilder.build(feedback_mode=FeedbackMode.SECURITY_AWARE, **common)
    self_correction = PromptBuilder.build(feedback_mode=FeedbackMode.SELF_CORRECTION, **common)
    assert "Dynamic security-test output" not in baseline
    assert "Static scanner output" not in baseline
    assert "Dynamic security-test output" in aware
    assert "Static scanner output" in aware
    assert "SECURITY POLICY" in aware
    assert "Self-review requirement" in self_correction
    assert "Static scanner output" not in self_correction
    assert "SECURITY POLICY" not in self_correction
