"""
AgentRegress — Base Scanner Interface
All scanners implement this interface for standardized output.
"""

from __future__ import annotations
import subprocess
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import uuid
import datetime

from regression.taxonomy import Vulnerability, VulnCategory, Severity, CWE_DATABASE


class BaseScanner(ABC):
    """Abstract base class for all security scanners."""

    name: str = "base"
    supported_languages: list[str] = []

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    @abstractmethod
    def scan(self) -> list[Vulnerability]:
        """Run the scanner and return a list of found vulnerabilities."""
        ...

    def is_available(self) -> bool:
        """Check if the scanner tool is installed and available."""
        try:
            result = subprocess.run(
                [self._tool_name(), "--version"],
                capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @abstractmethod
    def _tool_name(self) -> str:
        """Return the CLI tool name (e.g., 'bandit', 'semgrep')."""
        ...

    def _run_command(self, cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
        """Run a shell command and return (returncode, stdout, stderr)."""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, cwd=self.repo_path
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Timeout"
        except FileNotFoundError:
            return -1, "", f"Command not found: {cmd[0]}"

    def _make_vuln(
        self,
        cwe: str,
        file_path: str,
        line_number: Optional[int] = None,
        snippet: Optional[str] = None,
        severity_override: Optional[Severity] = None,
        description: str = "",
        iteration: int = 0,
    ) -> Vulnerability:
        """Helper to create a Vulnerability from a CWE ID."""
        entry = CWE_DATABASE.get(cwe)
        if entry:
            name = entry.name
            category = entry.category
            severity = severity_override or entry.default_severity
            ai_specific = entry.ai_specific
        else:
            name = cwe
            category = VulnCategory.SECURITY_MISCONFIGURATION
            severity = severity_override or Severity.MEDIUM
            ai_specific = False

        return Vulnerability(
            id=str(uuid.uuid4())[:8],
            cwe=cwe,
            name=name,
            category=category,
            severity=severity,
            file_path=file_path,
            line_number=line_number,
            snippet=snippet,
            tool=self.name,
            description=description or (entry.description if entry else ""),
            ai_specific=ai_specific,
            iteration=iteration,
            timestamp=datetime.datetime.utcnow().isoformat(),
        )


class MockScanner(BaseScanner):
    """
    Mock scanner for testing and demo purposes.
    Returns predefined vulnerability sets based on iteration.
    """

    name = "mock"

    def __init__(self, repo_path: str, mock_results: list[Vulnerability] = None):
        super().__init__(repo_path)
        self._mock_results = mock_results or []

    def scan(self) -> list[Vulnerability]:
        return self._mock_results

    def _tool_name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True
