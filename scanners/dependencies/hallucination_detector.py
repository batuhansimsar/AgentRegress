"""
AgentRegress — Package Hallucination Detector
Detects AI-hallucinated packages by checking PyPI and npm registries.
Also flags typosquatting and insecure version downgrades.
"""

from __future__ import annotations
import json
import re
import urllib.request
import urllib.error
from difflib import SequenceMatcher
from typing import Optional

from regression.taxonomy import Vulnerability, VulnCategory, Severity, SecurityShortcutType
from scanners.base_scanner import BaseScanner

# Well-known packages for typosquatting comparison
KNOWN_PYTHON_PACKAGES = [
    "requests", "flask", "django", "numpy", "pandas", "sqlalchemy",
    "pytest", "pydantic", "fastapi", "uvicorn", "celery", "redis",
    "boto3", "cryptography", "paramiko", "psycopg2", "pymongo",
    "httpx", "aiohttp", "click", "typer", "rich", "pyyaml",
    "python-jose", "passlib", "bcrypt", "itsdangerous", "jinja2",
    "werkzeug", "gunicorn", "alembic", "sqlmodel", "tortoise-orm",
    "jwt", "pyopenssl", "certifi", "urllib3", "setuptools",
]

KNOWN_NPM_PACKAGES = [
    "express", "react", "vue", "axios", "lodash", "moment",
    "jsonwebtoken", "bcrypt", "mongoose", "sequelize", "knex",
    "helmet", "cors", "dotenv", "passport", "jest", "mocha",
    "eslint", "webpack", "vite", "typescript", "prettier",
    "socket.io", "multer", "sharp", "stripe", "nodemailer",
]


def check_pypi(package_name: str) -> bool:
    """Return True if package exists on PyPI."""
    try:
        url = f"https://pypi.org/pypi/{package_name}/json"
        req = urllib.request.Request(url, headers={"User-Agent": "AgentRegress/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.HTTPError, urllib.error.URLError, Exception):
        return False


def check_npm(package_name: str) -> bool:
    """Return True if package exists on npm registry."""
    try:
        url = f"https://registry.npmjs.org/{package_name}"
        req = urllib.request.Request(url, headers={"User-Agent": "AgentRegress/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.HTTPError, urllib.error.URLError, Exception):
        return False


def typosquatting_similarity(package: str, known_packages: list[str]) -> tuple[float, Optional[str]]:
    """
    Find the closest known package by similarity ratio.
    Returns (similarity_score, closest_known_package).
    """
    best_score = 0.0
    best_match = None
    for known in known_packages:
        score = SequenceMatcher(None, package.lower(), known.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = known
    return best_score, best_match


def parse_requirements_txt(content: str) -> list[tuple[str, Optional[str]]]:
    """Parse requirements.txt and return list of (package_name, version)."""
    packages = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Handle ==, >=, <=, ~=, !=
        match = re.split(r"[=<>!~]+", line, maxsplit=1)
        pkg_name = match[0].strip()
        version = match[1].strip() if len(match) > 1 else None
        if pkg_name:
            packages.append((pkg_name, version))
    return packages


def parse_package_json(content: str) -> list[tuple[str, Optional[str]]]:
    """Parse package.json and return list of (package_name, version)."""
    try:
        data = json.loads(content)
        deps = {}
        deps.update(data.get("dependencies", {}))
        deps.update(data.get("devDependencies", {}))
        return [(name, ver) for name, ver in deps.items()]
    except json.JSONDecodeError:
        return []


class HallucinationDetector(BaseScanner):
    """
    Detects hallucinated or risky package installations.
    
    Detection modes:
    1. Package existence check (PyPI / npm)
    2. Typosquatting similarity  
    3. Version downgrade detection (compared to baseline)
    """

    name = "hallucination_detector"
    supported_languages = ["python", "javascript"]

    def __init__(
        self,
        repo_path: str,
        baseline_packages: Optional[dict[str, str]] = None,
        check_registry: bool = False,  # Set True to make real HTTP requests
        language: str = "python",
    ):
        super().__init__(repo_path)
        self.baseline_packages = baseline_packages or {}
        self.check_registry = check_registry
        self.language = language

    def _tool_name(self) -> str:
        return "hallucination_detector"

    def is_available(self) -> bool:
        return True  # Built-in, always available

    def scan(self) -> list[Vulnerability]:
        """Scan dependency files for hallucinated or risky packages."""
        import os
        vulns = []

        if self.language == "python":
            req_path = os.path.join(self.repo_path, "requirements.txt")
            if os.path.exists(req_path):
                with open(req_path) as f:
                    content = f.read()
                packages = parse_requirements_txt(content)
                vulns.extend(self._check_packages(packages, "requirements.txt", "pypi"))

        elif self.language == "javascript":
            pkg_path = os.path.join(self.repo_path, "package.json")
            if os.path.exists(pkg_path):
                with open(pkg_path) as f:
                    content = f.read()
                packages = parse_package_json(content)
                vulns.extend(self._check_packages(packages, "package.json", "npm"))

        return vulns

    def _check_packages(
        self,
        packages: list[tuple[str, Optional[str]]],
        source_file: str,
        registry: str,
    ) -> list[Vulnerability]:
        vulns = []
        known = KNOWN_PYTHON_PACKAGES if registry == "pypi" else KNOWN_NPM_PACKAGES
        check_fn = check_pypi if registry == "pypi" else check_npm

        for pkg_name, version in packages:
            # 1. Typosquatting check
            sim_score, closest = typosquatting_similarity(pkg_name, known)
            if closest and closest != pkg_name and sim_score >= 0.75 and sim_score < 1.0:
                vuln = self._make_vuln(
                    cwe="CWE-AI-001",
                    file_path=source_file,
                    description=(
                        f"Package '{pkg_name}' is suspiciously similar to '{closest}' "
                        f"(similarity: {sim_score:.0%}). Possible typosquatting or hallucination."
                    ),
                )
                vuln.ai_specific = True
                vulns.append(vuln)
                continue  # Don't also do registry check for flagged packages

            # 2. Registry existence check (optional, makes HTTP requests)
            if self.check_registry:
                exists = check_fn(pkg_name)
                if not exists:
                    vuln = self._make_vuln(
                        cwe="CWE-AI-001",
                        file_path=source_file,
                        description=(
                            f"Package '{pkg_name}' does not exist in {registry} registry. "
                            f"This may be an AI-hallucinated dependency."
                        ),
                    )
                    vuln.ai_specific = True
                    vulns.append(vuln)
                    continue

            # 3. Version downgrade check
            if version and pkg_name in self.baseline_packages:
                baseline_ver = self.baseline_packages[pkg_name]
                if self._is_downgrade(baseline_ver, version):
                    vuln = self._make_vuln(
                        cwe="CWE-AI-002",
                        file_path=source_file,
                        description=(
                            f"Package '{pkg_name}' was downgraded from "
                            f"'{baseline_ver}' to '{version}'. "
                            f"This may introduce known vulnerabilities."
                        ),
                        severity_override=Severity.MEDIUM,
                    )
                    vuln.ai_specific = True
                    vulns.append(vuln)

        return vulns

    @staticmethod
    def _is_downgrade(baseline: str, current: str) -> bool:
        """Simple version comparison: True if current < baseline."""
        def parse_ver(v: str) -> list[int]:
            parts = re.findall(r"\d+", v)
            return [int(p) for p in parts] if parts else [0]
        try:
            return parse_ver(current) < parse_ver(baseline)
        except Exception:
            return False
