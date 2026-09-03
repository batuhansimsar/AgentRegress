import subprocess
import sys

from benchmarks.loader import list_task_ids, load_manifest, load_task


def run_pytest(repo, paths):
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *paths],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_manifest_has_isolated_tasks_with_separate_expected_acceptance_states():
    manifest = load_manifest("benchmarks/manifest.yaml")
    assert list_task_ids(manifest) == ["A001", "A002", "A003", "B001"]
    for task_id in ("A001", "A002", "A003"):
        task = load_task(manifest, task_id)
        assert run_pytest(task.repo_path, task.functional_tests).returncode == 0
        assert run_pytest(task.repo_path, task.security_tests).returncode != 0
    functional_task = load_task(manifest, "B001")
    assert run_pytest(functional_task.repo_path, functional_task.functional_tests).returncode != 0
    assert run_pytest(functional_task.repo_path, functional_task.security_tests).returncode == 0
