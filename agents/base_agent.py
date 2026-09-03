"""Shared, evidence-preserving repair loop for AgentRegress agents."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from regression.metrics import ExperimentResult, IterationSnapshot
from regression.taxonomy import Vulnerability


class FeedbackMode(Enum):
    """The three explicitly distinct RQ6 feedback treatments."""

    BASELINE = "baseline"
    SECURITY_AWARE = "security_aware"
    SELF_CORRECTION = "self_correction"


@dataclass
class Task:
    """One manifest-defined task in an isolated working repository."""

    task_id: str
    task_type: str
    description: str
    repo_path: str
    functional_tests: list[str] = field(default_factory=list)
    security_tests: list[str] = field(default_factory=list)
    initial_vulns: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    editable_paths: list[str] = field(default_factory=list)
    build_commands: list[list[str]] = field(default_factory=list)

    def validate(self) -> None:
        if not self.functional_tests:
            raise ValueError(f"{self.task_id}: functional_tests must be configured")
        if not self.security_tests:
            raise ValueError(f"{self.task_id}: security_tests are mandatory for research runs")
        if not self.source_files:
            raise ValueError(f"{self.task_id}: source_files are mandatory for reproducible prompts")


@dataclass
class PatchApplyResult:
    applied: bool
    patch_content: str = ""
    files: list[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class IterationRecord:
    """Full-fidelity evidence for one pre- or post-repair repository state."""

    iteration: int
    git_sha: str
    prompt: str
    raw_response: str
    patch_applied: bool
    patch_content: str
    compiler_output: str
    test_output: str
    scanner_raw: dict
    vulnerabilities: list[Vulnerability]
    model_id: str
    temperature: float
    security_test_output: str = ""
    build_passed: Optional[bool] = None
    functional_tests_passed: Optional[bool] = None
    security_tests_passed: Optional[bool] = None
    patch_error: Optional[str] = None
    changed_files: list[str] = field(default_factory=list)
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: Optional[float] = None
    cost_usd: Optional[float] = None
    feedback_given: str = ""
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration, "git_sha": self.git_sha, "prompt": self.prompt,
            "raw_response": self.raw_response, "patch_applied": self.patch_applied,
            "patch_content": self.patch_content, "patch_error": self.patch_error,
            "changed_files": self.changed_files, "model_id": self.model_id,
            "temperature": self.temperature, "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens, "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd, "build_passed": self.build_passed,
            "functional_tests_passed": self.functional_tests_passed,
            "security_tests_passed": self.security_tests_passed,
            "compiler_output": self.compiler_output,
            "functional_test_output": self.test_output,
            "security_test_output": self.security_test_output,
            "scanner_raw": self.scanner_raw,
            "vulnerabilities": [vulnerability.to_dict() for vulnerability in self.vulnerabilities],
            "feedback_given": self.feedback_given, "timestamp": self.timestamp,
        }


class BaseAgent(ABC):
    """Abstract agent with deterministic build, test, security-test and scan checks."""

    model_id = "base"
    temperature = 0.0

    def __init__(self, api_key: Optional[str] = None, temperature: float = 0.0, max_tokens: int = 4096):
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._iteration_records: list[IterationRecord] = []

    @abstractmethod
    def call_llm(self, prompt: str) -> tuple[str, dict]:
        """Return response text and model metadata."""

    def run_repair_loop(
        self,
        task: Task,
        max_iterations: int = 5,
        feedback_mode: FeedbackMode = FeedbackMode.BASELINE,
        scanners: Optional[list] = None,
    ) -> tuple[ExperimentResult, list[IterationRecord]]:
        """Evaluate every repository state and require functional plus security success."""
        from regression.metrics import MetricsCalculator

        task.validate()
        self._iteration_records = []
        self._git_init_if_needed(task.repo_path)
        t0_sha = self._git_snapshot(task.repo_path, "AgentRegress t0: initial state")
        state = self._evaluate(task, scanners, 0)
        snapshots = [self._snapshot(0, "t0 — Initial", state)]
        self._iteration_records.append(self._make_record(
            0, t0_sha, "", "", PatchApplyResult(False), state, "baseline"
        ))

        for iteration in range(1, max_iterations + 1):
            prompt = self._build_prompt(
                task, iteration, feedback_mode,
                functional_feedback=state["functional"]["output"],
                build_feedback=state["build"]["output"],
                security_feedback=state["security"]["output"],
                scanner_feedback=self._format_scanner_feedback(state["vulnerabilities"]),
            )
            started = time.monotonic()
            try:
                response, meta = self.call_llm(prompt)
            except Exception as exc:
                response, meta = "", {"error": f"{type(exc).__name__}: {exc}"}
            latency_ms = round((time.monotonic() - started) * 1000, 1)
            patch = self._apply_structured_patch(task.repo_path, response, task)
            sha = self._git_snapshot(task.repo_path, f"AgentRegress t{iteration}: repair")
            state = self._evaluate(task, scanners, iteration)
            changed_files = self._get_changed_files(task.repo_path)
            snapshots.append(self._snapshot(iteration, f"t{iteration} — Agent repair #{iteration}", state, changed_files))
            self._iteration_records.append(self._make_record(
                iteration, sha, prompt, response, patch, state, self.model_id,
                meta, latency_ms, changed_files,
            ))
            if self._state_solved(state):
                break

        final = snapshots[-1]
        result = ExperimentResult(
            experiment_id=hashlib.md5(
                f"{self.model_id}:{task.task_id}:{datetime.datetime.now(datetime.UTC).isoformat()}".encode()
            ).hexdigest()[:12],
            agent_name=self.model_id,
            task_id=task.task_id,
            task_type=task.task_type,
            task_description=task.description,
            snapshots=snapshots,
            feedback_mode=feedback_mode.value,
            task_solved=self._snapshot_solved(final),
            final_build_passed=final.build_passed is True,
            final_functional_tests_passed=final.functional_tests_passed is True,
            final_security_tests_passed=final.security_tests_passed is True,
        )
        MetricsCalculator(result).compute_all()
        return result, self._iteration_records

    def _evaluate(self, task: Task, scanners: Optional[list], iteration: int) -> dict:
        # A same-second, same-size replacement can otherwise reuse an old .pyc
        # during the following pytest process and misattribute a stale test result
        # to the agent's patch.
        self._clear_bytecode(task.repo_path)
        build = self._run_build(task.repo_path, task)
        functional = self._run_tests(task.repo_path, task.functional_tests)
        security = self._run_tests(task.repo_path, task.security_tests)
        vulnerabilities, raw = self._run_scanners(task.repo_path, scanners, iteration)
        return {"build": build, "functional": functional, "security": security,
                "vulnerabilities": vulnerabilities, "scanner_raw": raw}

    @staticmethod
    def _clear_bytecode(repo: str) -> None:
        for bytecode in Path(repo).rglob("*.pyc"):
            bytecode.unlink(missing_ok=True)

    def _snapshot(self, iteration: int, label: str, state: dict, changed_files: Optional[list[str]] = None) -> IterationSnapshot:
        return IterationSnapshot(
            iteration=iteration, label=label, vulnerabilities=state["vulnerabilities"],
            changed_files=changed_files or [], agent_action="MODIFY" if iteration else None,
            feedback_received=self._classify_error(state["functional"]["output"]),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            build_passed=state["build"]["passed"],
            functional_tests_passed=state["functional"]["passed"],
            security_tests_passed=state["security"]["passed"],
        )

    def _make_record(
        self, iteration: int, sha: str, prompt: str, response: str, patch: PatchApplyResult,
        state: dict, model_id: str, meta: Optional[dict] = None, latency_ms: Optional[float] = None,
        changed_files: Optional[list[str]] = None,
    ) -> IterationRecord:
        meta = meta or {}
        return IterationRecord(
            iteration=iteration, git_sha=sha, prompt=prompt, raw_response=response,
            patch_applied=patch.applied, patch_content=patch.patch_content,
            patch_error=patch.error or meta.get("error"), changed_files=changed_files or [],
            compiler_output=state["build"]["output"], test_output=state["functional"]["output"],
            security_test_output=state["security"]["output"], scanner_raw=state["scanner_raw"],
            vulnerabilities=state["vulnerabilities"], model_id=model_id, temperature=self.temperature,
            build_passed=state["build"]["passed"], functional_tests_passed=state["functional"]["passed"],
            security_tests_passed=state["security"]["passed"],
            prompt_tokens=meta.get("prompt_tokens"), completion_tokens=meta.get("completion_tokens"),
            latency_ms=meta.get("latency_ms", latency_ms), cost_usd=meta.get("cost_usd"),
            feedback_given="\\n".join((
                state["build"]["output"], state["functional"]["output"], state["security"]["output"],
            )),
        )

    @staticmethod
    def _snapshot_solved(snapshot: IterationSnapshot) -> bool:
        return snapshot.build_passed is True and snapshot.functional_tests_passed is True and snapshot.security_tests_passed is True

    def _state_solved(self, state: dict) -> bool:
        return state["build"]["passed"] and state["functional"]["passed"] and state["security"]["passed"]

    def _build_prompt(
        self, task: Task, iteration: int, feedback_mode: FeedbackMode, functional_feedback: str,
        build_feedback: str, security_feedback: str, scanner_feedback: str,
    ) -> str:
        from agents.prompt_builder import PromptBuilder
        return PromptBuilder.build(
            task=task, iteration=iteration, feedback_mode=feedback_mode,
            functional_feedback=functional_feedback, build_feedback=build_feedback,
            security_feedback=security_feedback, scanner_feedback=scanner_feedback,
            source_context=self._source_context(task),
        )

    @staticmethod
    def _safe_repo_file(repo: str, relative_path: str) -> Path:
        root = Path(repo).resolve()
        candidate = (root / relative_path).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError(f"path escapes repository: {relative_path}")
        return candidate

    def _source_context(self, task: Task) -> str:
        sections = []
        for relative_path in task.source_files:
            try:
                content = self._safe_repo_file(task.repo_path, relative_path).read_text(encoding="utf-8")
                sections.append(f"### {relative_path}\\n~~~\\n{content[:12000]}\\n~~~")
            except (OSError, ValueError) as exc:
                sections.append(f"### {relative_path}\\n<unavailable: {exc}>")
        return "\\n\\n".join(sections)

    @staticmethod
    def _git_env() -> dict:
        return {**os.environ, "GIT_AUTHOR_NAME": "AgentRegress", "GIT_AUTHOR_EMAIL": "agentregress@research",
                "GIT_COMMITTER_NAME": "AgentRegress", "GIT_COMMITTER_EMAIL": "agentregress@research"}

    def _git_init_if_needed(self, repo: str) -> None:
        if not os.path.exists(os.path.join(repo, ".git")):
            subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=False)
            subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=False)
            subprocess.run(["git", "commit", "-m", "AgentRegress: initial state"], cwd=repo,
                           capture_output=True, check=False, env=self._git_env())

    def _git_snapshot(self, repo: str, message: str) -> str:
        subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=False, env=self._git_env())
        subprocess.run(["git", "commit", "--allow-empty", "-m", message], cwd=repo,
                       capture_output=True, check=False, env=self._git_env())
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()

    @staticmethod
    def _get_changed_files(repo: str) -> list[str]:
        result = subprocess.run(["git", "diff", "--name-only", "HEAD~1", "HEAD"], cwd=repo,
                                capture_output=True, text=True)
        return [path.strip() for path in result.stdout.splitlines() if path.strip()]

    def _run_build(self, repo: str, task: Task) -> dict:
        commands = task.build_commands or ([[sys.executable, "-m", "compileall", "-q", "."]]
                                            if any(Path(repo).rglob("*.py")) else [])
        if not commands:
            return {"passed": True, "output": "No build command configured."}
        outputs = []
        for command in commands:
            cmd = shlex.split(command) if isinstance(command, str) else command
            try:
                result = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                return {"passed": False, "output": "\\n".join(outputs + [f"$ {' '.join(cmd)}\\nBuild timeout (60s)"])}
            except OSError as exc:
                return {"passed": False, "output": "\\n".join(outputs + [f"$ {' '.join(cmd)}\\nBuild runner error: {exc}"])}
            outputs.append(f"$ {' '.join(cmd)}\\n{result.stdout}{result.stderr}")
            if result.returncode != 0:
                return {"passed": False, "output": "\\n".join(outputs)}
        return {"passed": True, "output": "\\n".join(outputs)}

    @staticmethod
    def _run_tests(repo: str, test_paths: list[str]) -> dict:
        if not test_paths:
            return {"passed": False, "output": "No tests configured."}
        try:
            result = subprocess.run([sys.executable, "-m", "pytest", "--tb=short", "-q", *test_paths],
                                    cwd=repo, capture_output=True, text=True, timeout=60)
            return {"passed": result.returncode == 0, "output": result.stdout + result.stderr}
        except subprocess.TimeoutExpired:
            return {"passed": False, "output": "Test timeout (60s)"}
        except OSError as exc:
            return {"passed": False, "output": f"Test runner error: {exc}"}

    def _run_scanners(self, repo: str, scanners: Optional[list], iteration: int) -> tuple[list[Vulnerability], dict]:
        if scanners is None:
            from scanners.dependencies.hallucination_detector import HallucinationDetector
            from scanners.sast.bandit_scanner import BanditScanner
            from scanners.secrets.secret_scanner import SecretScanner
            scanners = [BanditScanner(repo), SecretScanner(repo), HallucinationDetector(repo)]
        vulnerabilities, raw = [], {}
        for scanner in scanners:
            name = getattr(scanner, "name", scanner.__class__.__name__)
            try:
                findings, evidence = scanner.scan_with_raw()
                for finding in findings:
                    finding.iteration = iteration
                vulnerabilities.extend(findings)
                raw[name] = evidence
            except Exception as exc:
                raw[name] = {"error": f"{type(exc).__name__}: {exc}"}
        return vulnerabilities, raw

    @staticmethod
    def _format_scanner_feedback(vulnerabilities: list[Vulnerability]) -> str:
        if not vulnerabilities:
            return "Security scan: no issues found."
        lines = [f"Security scan found {len(vulnerabilities)} issue(s):"]
        for vulnerability in vulnerabilities[:20]:
            location = f"{vulnerability.file_path}:{vulnerability.line_number}" if vulnerability.line_number else vulnerability.file_path
            lines.append(f"- [{vulnerability.severity.name}] {vulnerability.cwe} {vulnerability.name} at {location}")
        return "\\n".join(lines)

    def _apply_structured_patch(self, repo: str, response: str, task: Task) -> PatchApplyResult:
        payload, error = self._parse_patch_payload(response)
        if error:
            return PatchApplyResult(False, error=error)
        assert payload is not None
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        patches = payload.get("patches")
        if not isinstance(patches, list) or not patches:
            return PatchApplyResult(False, content, error="patches must be a non-empty list")
        allowed, prepared, seen = set(task.editable_paths or task.source_files), [], set()
        try:
            for patch in patches:
                if not isinstance(patch, dict) or set(patch) != {"path", "content"}:
                    raise ValueError("each patch must contain exactly path and content")
                relative_path, replacement = patch["path"], patch["content"]
                if not isinstance(relative_path, str) or not isinstance(replacement, str):
                    raise ValueError("patch path and content must be strings")
                if not relative_path or Path(relative_path).is_absolute() or relative_path in seen:
                    raise ValueError("patch paths must be unique relative paths")
                if allowed and relative_path not in allowed:
                    raise ValueError(f"path is not editable for this task: {relative_path}")
                target = self._safe_repo_file(repo, relative_path)
                if not target.is_file():
                    raise ValueError(f"refusing to create a missing file: {relative_path}")
                if target.suffix == ".py":
                    compile(replacement, relative_path, "exec")
                prepared.append((target, relative_path, replacement))
                seen.add(relative_path)
        except (ValueError, SyntaxError) as exc:
            return PatchApplyResult(False, content, error=f"invalid structured patch: {exc}")
        temporary = []
        try:
            for target, _, replacement in prepared:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                                 prefix=".agentregress-", delete=False) as handle:
                    handle.write(replacement)
                    temporary.append((handle.name, target))
            for temporary_name, target in temporary:
                os.replace(temporary_name, target)
        except OSError as exc:
            for temporary_name, _ in temporary:
                Path(temporary_name).unlink(missing_ok=True)
            return PatchApplyResult(False, content, error=f"patch write failed: {exc}")
        return PatchApplyResult(True, content, [relative_path for _, relative_path, _ in prepared])

    @staticmethod
    def _parse_patch_payload(response: str) -> tuple[Optional[dict], Optional[str]]:
        fence = chr(96) * 3
        blocks = re.findall(rf"{fence}json\s*(.*?){fence}", response, flags=re.DOTALL | re.IGNORECASE)
        if len(blocks) != 1:
            return None, "response must contain exactly one fenced json block"
        try:
            payload = json.loads(blocks[0])
        except json.JSONDecodeError as exc:
            return None, f"invalid patch JSON: {exc.msg}"
        return (payload, None) if isinstance(payload, dict) else (None, "patch JSON must be an object")

    @staticmethod
    def _classify_error(output: str) -> Optional[str]:
        for needle, label in [
            ("modulenotfounderror", "ModuleNotFoundError"), ("importerror", "ImportError"),
            ("sslerror", "SSLError"), ("authenticationerror", "AuthenticationError"),
            ("permissionerror", "PermissionError"), ("databaseerror", "DatabaseError"),
            ("csrferror", "CSRFError"), ("connectionerror", "ConnectionError"),
            ("attributeerror", "AttributeError"), ("typeerror", "TypeError"),
        ]:
            if needle in output.lower():
                return label
        return "GenericError" if "failed" in output.lower() or "error" in output.lower() else None
