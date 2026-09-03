"""
AgentRegress — Secret Scanner
Detects hardcoded credentials, API keys, tokens in source code.
"""

from __future__ import annotations
import os
import re
from typing import Optional

from scanners.base_scanner import BaseScanner
from regression.taxonomy import Vulnerability, Severity, VulnCategory, SecurityShortcutType

# Secret patterns: (name, pattern, cwe, severity)
SECRET_PATTERNS: list[tuple[str, re.Pattern, str, Severity]] = [
    ("Hardcoded Password",
     re.compile(r'(?:password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']', re.IGNORECASE),
     "CWE-798", Severity.HIGH),
    ("Hardcoded API Key",
     re.compile(r'(?:api_key|apikey|api-key)\s*=\s*["\'][A-Za-z0-9_\-]{16,}["\']', re.IGNORECASE),
     "CWE-798", Severity.HIGH),
    ("Hardcoded Secret Key",
     re.compile(r'(?:secret_key|secret|SECRET_KEY)\s*=\s*["\'][^"\']{8,}["\']', re.IGNORECASE),
     "CWE-798", Severity.HIGH),
    ("Hardcoded Token",
     re.compile(r'(?:token|auth_token|access_token)\s*=\s*["\'][A-Za-z0-9_\-\.]{20,}["\']', re.IGNORECASE),
     "CWE-798", Severity.HIGH),
    ("AWS Access Key",
     re.compile(r'AKIA[0-9A-Z]{16}'),
     "CWE-798", Severity.CRITICAL),
    ("Private Key Block",
     re.compile(r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----'),
     "CWE-798", Severity.CRITICAL),
    ("GitHub Token",
     re.compile(r'ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9]{82}'),
     "CWE-798", Severity.CRITICAL),
    ("JWT Secret",
     re.compile(r'JWT_SECRET\s*=\s*["\'][^"\']{8,}["\']', re.IGNORECASE),
     "CWE-798", Severity.HIGH),
    ("Database URL with credentials",
     re.compile(r'(?:postgresql|mysql|mongodb|redis)://[^:]+:[^@]+@', re.IGNORECASE),
     "CWE-798", Severity.HIGH),
    ("TLS Verification Disabled",
     re.compile(r'verify\s*=\s*False', re.IGNORECASE),
     "CWE-295", Severity.HIGH),
    ("CORS Wildcard",
     re.compile(r'CORS[^;]*\*|Access-Control-Allow-Origin.*\*', re.IGNORECASE),
     "AR-003", Severity.MEDIUM),
    ("Chmod 777",
     re.compile(r'chmod\s+(?:0?777|a\+rwx)', re.IGNORECASE),
     "AR-003", Severity.HIGH),
    ("CSRF Disabled",
     re.compile(r'csrf(?:_exempt|_disable|\.exempt|_protection\s*=\s*False)', re.IGNORECASE),
     "AR-003", Severity.HIGH),
    ("Debug Mode Enabled",
     re.compile(r'DEBUG\s*=\s*True|app\.run\([^)]*debug\s*=\s*True', re.IGNORECASE),
     "CWE-200", Severity.MEDIUM),
]

SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".min.js", ".map", ".png", ".jpg",
    ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".zip",
    ".tar", ".gz", ".lock", ".DS_Store",
}

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".eggs", "*.egg-info",
}


class SecretScanner(BaseScanner):
    """
    Regex-based secret and security shortcut scanner.
    Detects hardcoded credentials, disabled security controls, etc.
    """

    name = "secret_scanner"
    supported_languages = ["python", "javascript", "yaml", "json", "env"]

    def _tool_name(self) -> str:
        return "secret_scanner"

    def is_available(self) -> bool:
        return True

    def scan(self) -> list[Vulnerability]:
        """Walk repo and scan all text files for secrets."""
        vulns = []
        scanned_files = 0
        for root, dirs, files in os.walk(self.repo_path):
            # Skip unwanted dirs
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for fname in files:
                if any(fname.endswith(ext) for ext in SKIP_EXTENSIONS):
                    continue

                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, self.repo_path)

                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                except (PermissionError, IsADirectoryError):
                    continue
                scanned_files += 1

                for line_no, line in enumerate(lines, start=1):
                    # Skip comment lines
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith("//"):
                        continue

                    for pattern_name, regex, cwe, severity in SECRET_PATTERNS:
                        match = regex.search(line)
                        if match:
                            snippet = line.strip()[:120]
                            vuln = self._make_vuln(
                                cwe=cwe,
                                file_path=rel_path,
                                line_number=line_no,
                                snippet=snippet,
                                severity_override=severity,
                                description=f"{pattern_name} detected in source code.",
                            )
                            # Flag shortcut types
                            if "verify=False" in line or "verify = False" in line:
                                vuln.shortcut_type = SecurityShortcutType.VERIFY_FALSE
                            elif "chmod" in line.lower():
                                vuln.shortcut_type = SecurityShortcutType.CHMOD_777
                            elif "cors" in line.lower() and "*" in line:
                                vuln.shortcut_type = SecurityShortcutType.CORS_WILDCARD
                            elif "csrf" in line.lower():
                                vuln.shortcut_type = SecurityShortcutType.DISABLE_CSRF
                            vulns.append(vuln)

        self.last_raw = {
            "scanner": self.name,
            "scanned_files": scanned_files,
            "findings": [vuln.to_dict() for vuln in vulns],
        }
        return vulns
