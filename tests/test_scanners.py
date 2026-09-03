import json

from scanners.dependencies.hallucination_detector import (
    HallucinationDetector,
    parse_requirements_txt,
    typosquatting_similarity,
)
from scanners.sast.bandit_scanner import BanditScanner


def test_bandit_parser_preserves_raw_tool_output(monkeypatch, tmp_path):
    scanner = BanditScanner(str(tmp_path))
    monkeypatch.setattr(scanner, "is_available", lambda: True)
    raw = json.dumps({
        "results": [{
            "test_id": "B602", "issue_severity": "HIGH", "filename": str(tmp_path / "app.py"),
            "line_number": 3, "code": "subprocess.run(value, shell=True)", "issue_text": "shell injection",
        }]
    })
    monkeypatch.setattr(scanner, "_run_command", lambda command: (1, raw, "scanner warning"))
    findings, evidence = scanner.scan_with_raw()
    assert findings[0].cwe == "CWE-78"
    assert evidence["stdout"] == raw
    assert evidence["parsed"]["results"][0]["test_id"] == "B602"


def test_hallucination_detector_parses_requirements_and_flags_typosquat(tmp_path):
    (tmp_path / "requirements.txt").write_text("reqeusts==2.0\nflask>=3.0\n", encoding="utf-8")
    detector = HallucinationDetector(str(tmp_path))
    findings, evidence = detector.scan_with_raw()
    assert parse_requirements_txt("flask>=3.0\n") == [("flask", "3.0")]
    assert typosquatting_similarity("reqeusts", ["requests"])[1] == "requests"
    assert any(finding.cwe == "AR-001" for finding in findings)
    assert evidence["inspected_files"][0]["path"] == "requirements.txt"
