import json

from agents.base_agent import BaseAgent, FeedbackMode, Task


class FakeAgent(BaseAgent):
    def __init__(self, response=""):
        super().__init__()
        self.response = response

    def call_llm(self, prompt):
        return self.response, {"prompt_tokens": 12, "completion_tokens": 8}


class FakeScanner:
    name = "fake"

    def scan_with_raw(self):
        return [], {"tool_output": "fake scan evidence"}


def patch_response(path, content):
    fence = chr(96) * 3
    return f"{fence}json\n{json.dumps({'patches': [{'path': path, 'content': content}]})}\n{fence}"


def test_structured_patch_rejects_path_escape_and_preserves_file(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    task = Task("T001", "type_b", "x", str(tmp_path), ["tests/functional"], ["tests/security"], source_files=["app.py"])
    result = FakeAgent()._apply_structured_patch(
        str(tmp_path),
        patch_response("../outside.py", "value = 2\n"),
        task,
    )
    assert not result.applied
    assert "editable" in result.error or "relative" in result.error
    assert target.read_text(encoding="utf-8") == "value = 1\n"


def test_structured_patch_rejects_invalid_python_without_mutating(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    task = Task("T001", "type_b", "x", str(tmp_path), ["tests/functional"], ["tests/security"], source_files=["app.py"])
    result = FakeAgent()._apply_structured_patch(
        str(tmp_path),
        patch_response("app.py", "def broken(:\n"),
        task,
    )
    assert not result.applied
    assert "invalid structured patch" in result.error
    assert target.read_text(encoding="utf-8") == "value = 1\n"


def test_repair_loop_records_build_security_and_raw_scanner_evidence(tmp_path):
    (tmp_path / "tests" / "functional").mkdir(parents=True)
    (tmp_path / "tests" / "security").mkdir(parents=True)
    (tmp_path / "app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (tmp_path / "tests" / "functional" / "test_value.py").write_text(
        "from app import value\n\ndef test_value():\n    assert value() == 2\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "security" / "test_value_security.py").write_text(
        "from app import value\n\ndef test_security_acceptance():\n    assert value() == 2\n", encoding="utf-8"
    )
    task = Task(
        "T002", "type_b", "fix value", str(tmp_path),
        ["tests/functional"], ["tests/security"],
        source_files=["app.py"], editable_paths=["app.py"],
    )
    agent = FakeAgent(patch_response("app.py", "def value():\n    return 2\n"))
    result, records = agent.run_repair_loop(task, max_iterations=1, scanners=[FakeScanner()])
    final_record = records[-1]
    assert result.task_solved
    assert result.final_secure
    assert final_record.compiler_output
    assert final_record.functional_tests_passed is True
    assert final_record.security_tests_passed is True
    assert final_record.scanner_raw == {"fake": {"tool_output": "fake scan evidence"}}
