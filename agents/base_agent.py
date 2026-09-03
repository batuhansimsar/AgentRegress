"""
AgentRegress — Base Agent Interface
Defines the abstract repair loop that all agent implementations follow.
"""

from __future__ import annotations
import os
import subprocess
import json
import datetime
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from regression.taxonomy import Vulnerability
from regression.metrics import IterationSnapshot, ExperimentResult


class FeedbackMode(Enum):
    """
    Controls what feedback the agent sees at each iteration.
    Maps to Exp1, Exp2, Exp3 in the paper.
    """
    BASELINE = "baseline"               # Exp1: compiler + test output only
    SECURITY_AWARE = "security_aware"   # Exp2: + SAST + dependency + security policy
    SELF_CORRECTION = "self_correction" # Exp3: + "review your changes for security"


@dataclass
class Task:
    """A benchmark repair task."""
    task_id: str
    task_type: str          # "type_a", "type_b", "type_c"
    description: str        # The instruction given to the agent
    repo_path: str          # Absolute path to the repo to work on
    functional_tests: list[str] = field(default_factory=list)   # pytest paths
    security_tests: list[str] = field(default_factory=list)     # security test paths
    initial_vulns: list[str] = field(default_factory=list)      # CWE IDs at t0


@dataclass
class IterationRecord:
    """
    Complete record of one agent iteration for reproducibility.
    This is the full-fidelity log — ExperimentResult stores aggregated metrics.
    """
    iteration: int
    git_sha: str                    # Snapshot SHA before/after patch
    prompt: str                     # Full prompt sent to the model
    raw_response: str               # Full LLM response text
    patch_applied: bool             # Whether the patch was successfully applied
    patch_content: str              # The actual code changes
    compiler_output: str            # stdout/stderr of build
    test_output: str                # pytest output
    scanner_raw: dict               # Raw scanner JSON output
    vulnerabilities: list[Vulnerability]
    model_id: str
    temperature: float
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: Optional[float] = None
    cost_usd: Optional[float] = None
    feedback_given: str = ""        # The feedback string shown to agent
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "git_sha": self.git_sha,
            "patch_applied": self.patch_applied,
            "patch_content": self.patch_content,
            "model_id": self.model_id,
            "temperature": self.temperature,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "compiler_output": self.compiler_output[:2000],     # truncate for storage
            "test_output": self.test_output[:2000],
            "feedback_given": self.feedback_given[:1000],
            "n_vulnerabilities": len(self.vulnerabilities),
            "vulnerability_cwes": [v.cwe for v in self.vulnerabilities],
            "timestamp": self.timestamp,
        }


class BaseAgent(ABC):
    """
    Abstract base class for all coding agents.

    Subclasses implement `call_llm()` to invoke their specific model API.
    The repair loop logic (snapshot, prompt, patch, test, scan, iterate) is
    implemented here and shared by all agents.
    """

    model_id: str = "base"
    temperature: float = 0.0

    def __init__(
        self,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ):
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._iteration_records: list[IterationRecord] = []

    # ── Abstract: subclasses implement this ───────────────────────────────────

    @abstractmethod
    def call_llm(self, prompt: str) -> tuple[str, dict]:
        """
        Call the LLM with the given prompt.
        Returns: (response_text, metadata_dict)
        metadata_dict should include: prompt_tokens, completion_tokens, latency_ms, cost_usd
        """
        ...

    # ── Main Repair Loop ──────────────────────────────────────────────────────

    def run_repair_loop(
        self,
        task: Task,
        max_iterations: int = 5,
        feedback_mode: FeedbackMode = FeedbackMode.BASELINE,
        scanners: Optional[list] = None,
    ) -> tuple[ExperimentResult, list[IterationRecord]]:
        """
        Run the full iterative repair loop.

        Each iteration:
          1. Git snapshot (commit current state)
          2. Run functional + security tests
          3. Run security scanners
          4. Build feedback string
          5. Call LLM with prompt + feedback
          6. Apply patch
          7. Record IterationSnapshot

        Returns (ExperimentResult, full_iteration_records)
        """
        from regression.metrics import MetricsCalculator

        repo = task.repo_path
        self._iteration_records = []
        snapshots: list[IterationSnapshot] = []

        # ── t0: Initial snapshot ─────────────────────────────────────────────
        self._git_init_if_needed(repo)
        t0_sha = self._git_snapshot(repo, "AgentRegress t0: initial state")
        t0_vulns = self._run_scanners(repo, scanners, iteration=0)
        t0_tests = self._run_tests(repo, task.functional_tests)

        snapshots.append(IterationSnapshot(
            iteration=0,
            label="t0 — Initial",
            vulnerabilities=t0_vulns,
            changed_files=[],
            agent_action=None,
            feedback_received=None,
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        ))

        # ── Repair loop ───────────────────────────────────────────────────────
        current_feedback = t0_tests.get("output", "")
        task_solved = False

        for i in range(1, max_iterations + 1):
            # Build scanner output for security-aware mode
            scanner_feedback = ""
            if feedback_mode in (FeedbackMode.SECURITY_AWARE, FeedbackMode.SELF_CORRECTION):
                scanner_feedback = self._format_scanner_feedback(t0_vulns if i == 1 else snapshots[-1].vulnerabilities)

            # Build full prompt
            prompt = self._build_prompt(
                task=task,
                iteration=i,
                feedback_mode=feedback_mode,
                functional_feedback=current_feedback,
                scanner_feedback=scanner_feedback,
                previous_response="",
            )

            # Call LLM
            import time
            t_start = time.time()
            response_text, llm_meta = self.call_llm(prompt)
            latency_ms = (time.time() - t_start) * 1000

            # Apply patch
            patch_content = self._extract_code_blocks(response_text)
            patch_applied = self._apply_patch(repo, patch_content, task)

            # Snapshot after patch
            git_sha = self._git_snapshot(repo, f"AgentRegress t{i}: agent repair #{i}")
            changed_files = self._get_changed_files(repo, git_sha)

            # Run tests + scan
            test_result = self._run_tests(repo, task.functional_tests)
            current_feedback = test_result.get("output", "")
            vulns = self._run_scanners(repo, scanners, iteration=i)

            # Check if task solved (all functional tests pass)
            task_solved = test_result.get("passed", False)

            snap = IterationSnapshot(
                iteration=i,
                label=f"t{i} — Agent repair #{i}",
                vulnerabilities=vulns,
                changed_files=changed_files,
                agent_action="MODIFY",
                feedback_received=self._classify_error(current_feedback),
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            )
            snapshots.append(snap)

            # Full record for reproducibility
            record = IterationRecord(
                iteration=i,
                git_sha=git_sha,
                prompt=prompt,
                raw_response=response_text,
                patch_applied=patch_applied,
                patch_content=patch_content,
                compiler_output="",
                test_output=current_feedback,
                scanner_raw={},
                vulnerabilities=vulns,
                model_id=self.model_id,
                temperature=self.temperature,
                prompt_tokens=llm_meta.get("prompt_tokens"),
                completion_tokens=llm_meta.get("completion_tokens"),
                latency_ms=latency_ms,
                cost_usd=llm_meta.get("cost_usd"),
                feedback_given=current_feedback[:500],
            )
            self._iteration_records.append(record)

            # Stop if solved and final scan is clean
            if task_solved and len(vulns) == 0:
                break

        # ── Build ExperimentResult ─────────────────────────────────────────────
        exp_id = hashlib.md5(
            f"{self.model_id}:{task.task_id}:{datetime.datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]

        result = ExperimentResult(
            experiment_id=exp_id,
            agent_name=self.model_id,
            task_id=task.task_id,
            task_type=task.task_type,
            task_description=task.description,
            snapshots=snapshots,
            task_solved=task_solved,
            final_secure=len(snapshots[-1].vulnerabilities) == 0,
        )

        calc = MetricsCalculator(result)
        calc.compute_all()

        return result, self._iteration_records

    # ── Prompt Building ────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        task: Task,
        iteration: int,
        feedback_mode: FeedbackMode,
        functional_feedback: str,
        scanner_feedback: str,
        previous_response: str,
    ) -> str:
        from agents.prompt_builder import PromptBuilder
        return PromptBuilder.build(
            task=task,
            iteration=iteration,
            feedback_mode=feedback_mode,
            functional_feedback=functional_feedback,
            scanner_feedback=scanner_feedback,
        )

    # ── Git Utilities ──────────────────────────────────────────────────────────

    def _git_init_if_needed(self, repo: str) -> None:
        """Initialize git in repo if not already a git repo."""
        git_dir = os.path.join(repo, ".git")
        if not os.path.exists(git_dir):
            subprocess.run(["git", "init"], cwd=repo, capture_output=True)
            subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "AgentRegress: initial state"],
                cwd=repo, capture_output=True,
                env={**os.environ, "GIT_AUTHOR_NAME": "AgentRegress",
                     "GIT_AUTHOR_EMAIL": "agentregress@research",
                     "GIT_COMMITTER_NAME": "AgentRegress",
                     "GIT_COMMITTER_EMAIL": "agentregress@research"},
            )

    def _git_snapshot(self, repo: str, message: str) -> str:
        """Commit current state and return the SHA."""
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "AgentRegress",
            "GIT_AUTHOR_EMAIL": "agentregress@research",
            "GIT_COMMITTER_NAME": "AgentRegress",
            "GIT_COMMITTER_EMAIL": "agentregress@research",
        }
        subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, env=env)
        subprocess.run(["git", "commit", "--allow-empty", "-m", message],
                       cwd=repo, capture_output=True, env=env)
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo, capture_output=True, text=True
        )
        return result.stdout.strip()

    def _get_changed_files(self, repo: str, current_sha: str) -> list[str]:
        """Get list of files changed in the last commit."""
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            cwd=repo, capture_output=True, text=True
        )
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]

    # ── Test Runner ────────────────────────────────────────────────────────────

    def _run_tests(self, repo: str, test_paths: list[str]) -> dict:
        """Run pytest and return {passed: bool, output: str}."""
        if not test_paths:
            return {"passed": True, "output": "No tests configured."}
        cmd = ["python", "-m", "pytest", "--tb=short", "-q"] + test_paths
        try:
            result = subprocess.run(
                cmd, cwd=repo, capture_output=True, text=True, timeout=60
            )
            passed = result.returncode == 0
            return {"passed": passed, "output": result.stdout + result.stderr}
        except subprocess.TimeoutExpired:
            return {"passed": False, "output": "Test timeout (60s)"}
        except Exception as e:
            return {"passed": False, "output": f"Test runner error: {e}"}

    # ── Scanner Runner ─────────────────────────────────────────────────────────

    def _run_scanners(
        self, repo: str, scanners: Optional[list], iteration: int
    ) -> list[Vulnerability]:
        """Run all configured scanners and return combined vulnerability list."""
        if not scanners:
            # Default: BanditScanner + SecretScanner
            from scanners.sast.bandit_scanner import BanditScanner
            from scanners.secrets.secret_scanner import SecretScanner
            scanners = [BanditScanner(repo), SecretScanner(repo)]

        vulns = []
        for scanner in scanners:
            try:
                found = scanner.scan()
                for v in found:
                    v.iteration = iteration
                vulns.extend(found)
            except Exception as e:
                print(f"[Scanner {scanner.name}] Error: {e}")
        return vulns

    def _format_scanner_feedback(self, vulns: list[Vulnerability]) -> str:
        """Format scanner results as readable feedback for the agent."""
        if not vulns:
            return "Security scan: No issues found."
        lines = [f"Security scan found {len(vulns)} issue(s):"]
        for v in vulns[:10]:  # limit to 10 to avoid context overflow
            lines.append(
                f"  - [{v.severity.name}] {v.cwe} {v.name} "
                f"in {v.file_path}"
                + (f":{v.line_number}" if v.line_number else "")
            )
        return "\n".join(lines)

    # ── Code Extraction + Patch Application ───────────────────────────────────

    def _extract_code_blocks(self, response: str) -> str:
        """Extract code from LLM response (fenced code blocks or raw code)."""
        import re
        # Extract ```python ... ``` or ``` ... ``` blocks
        blocks = re.findall(r"```(?:python|py)?\n(.*?)```", response, re.DOTALL)
        if blocks:
            return "\n\n# --- BLOCK SEPARATOR ---\n\n".join(blocks)
        return response  # Return full response if no code blocks found

    def _apply_patch(self, repo: str, patch_content: str, task: Task) -> bool:
        """
        Apply the agent's code change to the repository.

        Strategy:
        1. Look for file path comments in the response (# file: app.py)
        2. If found, overwrite that file
        3. Otherwise, use heuristic: find most likely target file
        Returns True if applied successfully.
        """
        import re

        if not patch_content.strip():
            return False

        # Look for file path hint: "# file: path/to/file.py" or "# === path/to/file.py ==="
        file_pattern = re.compile(
            r"#\s*(?:file|===|path):\s*([^\s\n]+\.(?:py|js|ts|json|yaml|yml|txt))",
            re.IGNORECASE
        )
        target_files = file_pattern.findall(patch_content)

        if target_files:
            target_file = os.path.join(repo, target_files[0])
            try:
                # Extract just the code (remove the file hint comment)
                code = re.sub(r"#\s*(?:file|===|path):\s*\S+\n?", "", patch_content).strip()
                with open(target_file, "w") as f:
                    f.write(code)
                return True
            except Exception as e:
                print(f"[PatchApplier] Failed to write {target_file}: {e}")
                return False

        # Heuristic: apply to the most recently modified Python file
        try:
            result = subprocess.run(
                ["git", "log", "--name-only", "--pretty=format:", "-1"],
                cwd=repo, capture_output=True, text=True
            )
            last_files = [f.strip() for f in result.stdout.splitlines() if f.strip().endswith(".py")]
            if last_files:
                target_file = os.path.join(repo, last_files[0])
                with open(target_file, "w") as f:
                    f.write(patch_content)
                return True
        except Exception:
            pass

        # Last resort: look for .py files in repo root
        py_files = [f for f in os.listdir(repo) if f.endswith(".py") and not f.startswith("test_")]
        if py_files:
            target_file = os.path.join(repo, py_files[0])
            try:
                with open(target_file, "w") as f:
                    f.write(patch_content)
                return True
            except Exception:
                pass

        return False

    @staticmethod
    def _classify_error(test_output: str) -> Optional[str]:
        """Classify the type of error seen in test output (for RQ3 analysis)."""
        output_lower = test_output.lower()
        error_patterns = [
            ("ModuleNotFoundError", "ModuleNotFoundError"),
            ("ImportError", "ImportError"),
            ("SSLError", "SSLError"),
            ("AuthenticationError", "AuthenticationError"),
            ("PermissionError", "PermissionError"),
            ("DatabaseError", "DatabaseError"),
            ("CORSError", "CORSError"),
            ("CSRFError", "CSRFError"),
            ("ConnectionError", "ConnectionError"),
            ("AttributeError", "AttributeError"),
            ("TypeError", "TypeError"),
        ]
        for pattern, label in error_patterns:
            if pattern.lower() in output_lower:
                return label
        if "failed" in output_lower or "error" in output_lower:
            return "GenericError"
        return None
