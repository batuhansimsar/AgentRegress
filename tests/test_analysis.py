import json

from analysis.analyze_runs import analyze


def test_analysis_writes_csv_and_parquet_for_a_clean_real_run(tmp_path):
    result_dir = tmp_path / "results" / "run" / "A001"
    result_dir.mkdir(parents=True)
    payload = {
        "data_kind": "real",
        "experiment": {
            "experiment_id": "run-a001", "agent_name": "gemini", "feedback_mode": "baseline",
            "task_id": "A001", "task_type": "type_a", "task_solved": True, "final_secure": True,
            "final_build_passed": True, "final_functional_tests_passed": True,
            "final_security_tests_passed": True, "metrics": {
                "srr": 0.0, "frr": 1.0, "rsc": 0.0, "security_churn": 0,
                "total_fixed": 1, "total_introduced": 0,
            },
            "snapshots": [{}, {}], "regression_events": [],
        },
    }
    (result_dir / "result.json").write_text(json.dumps(payload), encoding="utf-8")
    output_dir = tmp_path / "analysis"
    analyze(tmp_path / "results", output_dir)
    assert (output_dir / "runs.csv").exists()
    assert (output_dir / "runs.parquet").exists()
    assert (output_dir / "regression_events.parquet").exists()
    assert (output_dir / "rq_tables.md").exists()
