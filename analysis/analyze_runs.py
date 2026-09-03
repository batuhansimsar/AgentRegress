#!/usr/bin/env python3
"""Turn real run evidence into CSV/Parquet, bootstrap summaries and RQ tables."""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean, pstdev


ROOT = Path(__file__).resolve().parents[1]
EVENT_FIELDS = [
    "experiment_id", "agent_name", "feedback_mode", "task_id", "task_type",
    "iteration", "introduced_cwe", "introduced_category", "severity", "distance",
]


def bootstrap_mean_ci(values: list[float], samples: int = 2_000, seed: int = 20260903) -> tuple[float | None, float | None, float | None]:
    if not values:
        return None, None, None
    mean = fmean(values)
    if len(values) == 1:
        return mean, mean, mean
    rng = random.Random(seed)
    means = sorted(fmean(rng.choices(values, k=len(values))) for _ in range(samples))
    return mean, means[int(samples * 0.025)], means[int(samples * 0.975)]


def cohens_d(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(right) < 2:
        return None
    left_var, right_var = pstdev(left) ** 2, pstdev(right) ** 2
    pooled = (((len(left) - 1) * left_var) + ((len(right) - 1) * right_var)) / (len(left) + len(right) - 2)
    return None if pooled == 0 else (fmean(right) - fmean(left)) / pooled**0.5


def load_rows(results_dir: Path) -> tuple[list[dict], list[dict]]:
    runs, events = [], []
    for path in sorted(results_dir.rglob("result.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("data_kind") != "real":
            continue
        experiment = payload["experiment"]
        row = {
            "source_file": str(path), "experiment_id": experiment["experiment_id"],
            "agent_name": experiment["agent_name"], "feedback_mode": experiment["feedback_mode"],
            "task_id": experiment["task_id"], "task_type": experiment["task_type"],
            "task_solved": experiment["task_solved"], "final_secure": experiment["final_secure"],
            "final_build_passed": experiment["final_build_passed"],
            "final_functional_tests_passed": experiment["final_functional_tests_passed"],
            "final_security_tests_passed": experiment["final_security_tests_passed"],
            "iterations": len(experiment["snapshots"]) - 1, **experiment["metrics"],
        }
        runs.append(row)
        for event in experiment["regression_events"]:
            events.append({
                "experiment_id": experiment["experiment_id"], "agent_name": experiment["agent_name"],
                "feedback_mode": experiment["feedback_mode"], "task_id": experiment["task_id"],
                "task_type": experiment["task_type"], "iteration": event["iteration_to"],
                "introduced_cwe": event["introduced"]["cwe"],
                "introduced_category": event["introduced"]["category"],
                "severity": event["introduced"]["severity"], "distance": event["distance"],
            })
    return runs, events


def grouped_metric(rows: list[dict], group_fields: list[str], metric: str, rq: str) -> list[dict]:
    groups: dict[tuple, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get(metric)
        if isinstance(value, (int, float)):
            groups[tuple(row[field] for field in group_fields)].append(float(value))
    output = []
    for key, values in sorted(groups.items()):
        mean, low, high = bootstrap_mean_ci(values, seed=20260903 + len(output))
        output.append({"rq": rq, "metric": metric, **dict(zip(group_fields, key)), "n": len(values),
                       "mean": mean, "ci95_low": low, "ci95_high": high})
    return output


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_rq_markdown(path: Path, tables: list[dict]) -> None:
    lines = ["# Automatically generated real-run RQ tables", "", "Only real experiment artifacts are included.", ""]
    for rq in sorted({row["rq"] for row in tables}):
        rows = [row for row in tables if row["rq"] == rq]
        lines.extend([f"## {rq}", "", "| Metric | Group | n | Mean | 95% bootstrap CI |", "|---|---|---:|---:|---|"])
        for row in rows:
            group = ", ".join(f"{key}={value}" for key, value in row.items()
                              if key in {"agent_name", "feedback_mode", "task_type", "introduced_cwe", "iteration"})
            mean = "—" if row.get("mean") is None else f"{row['mean']:.4f}"
            interval = "—" if row.get("ci95_low") is None else f"[{row['ci95_low']:.4f}, {row['ci95_high']:.4f}]"
            lines.append(f"| {row['metric']} | {group} | {row['n']} | {mean} | {interval} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def analyze(results_dir: Path, output_dir: Path) -> None:
    runs, events = load_rows(results_dir)
    if not runs:
        raise ValueError(f"No real result.json files found under {results_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "runs.csv", runs)
    write_csv(output_dir / "regression_events.csv", events, EVENT_FIELDS)
    try:
        import pandas as pd
        pd.DataFrame(runs).to_parquet(output_dir / "runs.parquet", index=False)
        pd.DataFrame(events, columns=EVENT_FIELDS).to_parquet(output_dir / "regression_events.parquet", index=False)
    except ImportError as exc:
        raise RuntimeError("Parquet export requires pandas and pyarrow; install requirements.txt") from exc

    tables = []
    tables.extend(grouped_metric(runs, ["agent_name"], "srr", "RQ1: regression frequency"))
    for cwe, count in sorted(Counter(event["introduced_cwe"] for event in events).items()):
        tables.append({"rq": "RQ2: introduced vulnerability types", "metric": "introduced_count",
                       "introduced_cwe": cwe, "n": count, "mean": float(count),
                       "ci95_low": float(count), "ci95_high": float(count)})
    tables.extend(grouped_metric(runs, ["task_type"], "srr", "RQ3: task-type association"))
    for iteration, count in sorted(Counter(event["iteration"] for event in events).items()):
        tables.append({"rq": "RQ4: iteration dynamics", "metric": "introduced_count",
                       "iteration": iteration, "n": count, "mean": float(count),
                       "ci95_low": float(count), "ci95_high": float(count)})
    tables.extend(grouped_metric(runs, ["agent_name"], "srr", "RQ5: model comparison"))
    tables.extend(grouped_metric(runs, ["feedback_mode"], "srr", "RQ6: feedback treatment"))

    baseline, treatments = defaultdict(list), defaultdict(list)
    for row in runs:
        value = row.get("srr")
        if not isinstance(value, (int, float)):
            continue
        if row["feedback_mode"] == "baseline":
            baseline[row["agent_name"]].append(float(value))
        else:
            treatments[(row["agent_name"], row["feedback_mode"])].append(float(value))
    effects = []
    for (agent, mode), values in sorted(treatments.items()):
        reference = baseline[agent]
        effects.append({
            "agent_name": agent, "feedback_mode": mode, "metric": "srr",
            "baseline_n": len(reference), "treatment_n": len(values),
            "mean_difference": fmean(values) - fmean(reference) if reference else None,
            "cohens_d": cohens_d(reference, values),
        })
    write_csv(output_dir / "effect_sizes.csv", effects)
    write_csv(output_dir / "rq_tables.csv", tables)
    write_rq_markdown(output_dir / "rq_tables.md", tables)
    (output_dir / "summary.json").write_text(json.dumps({
        "data_kind": "real", "n_runs": len(runs), "n_regression_events": len(events),
        "source_results_dir": str(results_dir.resolve()),
    }, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze AgentRegress real experiment evidence.")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results" / "real")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "analysis" / "output")
    args = parser.parse_args()
    analyze(args.results_dir, args.output_dir)
    print(f"Analysis written to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
