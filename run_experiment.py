#!/usr/bin/env python3
"""Run one or more real AgentRegress benchmark experiments.

Each benchmark fixture is copied to results/real/<run-id>/<task-id>/repo before
the agent starts. The source fixtures therefore remain immutable across trials.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import shutil
import sys
from pathlib import Path

from agents.base_agent import FeedbackMode
from agents.gemini_agent import GeminiAgent
from benchmarks.loader import list_task_ids, load_manifest, load_task
from regression.metrics import ExperimentResult


ROOT = Path(__file__).resolve().parent


def _json_number(value: float) -> float | None:
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def serialize_result(result: ExperimentResult, records: list) -> dict:
    """Persist metrics, snapshots and full raw iteration evidence."""
    return {
        "schema_version": "1.0",
        "data_kind": "real",
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "experiment": {
            "experiment_id": result.experiment_id,
            "agent_name": result.agent_name,
            "feedback_mode": result.feedback_mode,
            "task_id": result.task_id,
            "task_type": result.task_type,
            "task_description": result.task_description,
            "task_solved": result.task_solved,
            "final_secure": result.final_secure,
            "final_build_passed": result.final_build_passed,
            "final_functional_tests_passed": result.final_functional_tests_passed,
            "final_security_tests_passed": result.final_security_tests_passed,
            "metrics": {
                "srr": _json_number(result.srr),
                "frr": _json_number(result.frr),
                "rsc": _json_number(result.rsc),
                "security_churn": result.security_churn,
                "total_fixed": result.total_fixed,
                "total_introduced": result.total_introduced,
            },
            "snapshots": [
                {
                    "iteration": snapshot.iteration,
                    "label": snapshot.label,
                    "changed_files": snapshot.changed_files,
                    "build_passed": snapshot.build_passed,
                    "functional_tests_passed": snapshot.functional_tests_passed,
                    "security_tests_passed": snapshot.security_tests_passed,
                    "vulnerabilities": [vulnerability.to_dict() for vulnerability in snapshot.vulnerabilities],
                }
                for snapshot in result.snapshots
            ],
            "regression_events": [
                {
                    "introduced": event.introduced_vuln.to_dict(),
                    "iteration_from": event.iteration_from,
                    "iteration_to": event.iteration_to,
                    "distance": event.distance.value if event.distance else None,
                    "is_cross_class": event.is_cross_class,
                    "is_migration": event.is_migration,
                    "fixed_vuln_cwe": event.fixed_vuln_cwe,
                }
                for event in result.regression_events
            ],
        },
        "iteration_records": [record.to_dict() for record in records],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an AgentRegress real experiment.")
    parser.add_argument("--agent", choices=["gemini"], required=True)
    parser.add_argument("--model", default="gemini-2.5-flash")
    parser.add_argument("--task", default="all", help="Task ID from the manifest, or 'all'.")
    parser.add_argument("--mode", choices=[mode.value for mode in FeedbackMode], default="baseline")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--manifest", type=Path, default=ROOT / "benchmarks" / "manifest.yaml")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results" / "real")
    parser.add_argument("--run-id", help="Optional reproducible run label; must not already exist.")
    parser.add_argument("--dry-run", action="store_true", help="Validate fixtures and copy no agent data.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.iterations < 1:
        raise ValueError("--iterations must be at least 1")
    manifest = load_manifest(args.manifest)
    task_ids = list_task_ids(manifest) if args.task == "all" else [args.task]
    unknown = set(task_ids) - set(list_task_ids(manifest))
    if unknown:
        raise ValueError(f"Unknown task(s): {', '.join(sorted(unknown))}")

    run_id = args.run_id or datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = args.results_dir.resolve() / run_id
    if run_root.exists():
        raise FileExistsError(f"Refusing to overwrite existing run directory: {run_root}")
    if args.dry_run:
        for task_id in task_ids:
            task = load_task(manifest, task_id)
            task.validate()
            print(f"validated {task.task_id}: {task.repo_path}")
        return 0

    mode = FeedbackMode(args.mode)
    agent = GeminiAgent(model=args.model)
    if not agent.api_key:
        raise EnvironmentError("GEMINI_API_KEY is required; export it or add it to a local .env file")
    run_root.mkdir(parents=True)
    for task_id in task_ids:
        fixture_task = load_task(manifest, task_id)
        repo_copy = run_root / task_id / "repo"
        shutil.copytree(fixture_task.repo_path, repo_copy, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        task = load_task(manifest, task_id, repo_path=repo_copy)
        result, records = agent.run_repair_loop(
            task=task,
            max_iterations=args.iterations,
            feedback_mode=mode,
        )
        output = run_root / task_id / "result.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(serialize_result(result, records), indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            f"{task_id}: solved={result.task_solved} secure={result.final_secure} "
            f"iterations={len(result.snapshots) - 1} -> {output}"
        )
    print(f"Real experiment evidence written to {run_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
