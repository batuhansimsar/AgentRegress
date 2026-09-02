"""
AgentRegress — Bandit SAST Scanner
Runs Bandit on Python code and maps results to AgentRegress taxonomy.
"""

from __future__ import annotations
import json
from typing import Optional

from scanners.base_scanner import BaseScanner
from regression.taxonomy import Vulnerability, Severity

# Bandit issue ID → CWE mapping
BANDIT_TO_CWE: dict[str, str] = {
    "B101": "CWE-617",   # assert used
    "B102": "CWE-78",    # use of exec
    "B103": "CWE-732",   # setting permissions
    "B104": "CWE-605",   # binding to all interfaces
    "B105": "CWE-798",   # hardcoded password (string)
    "B106": "CWE-798",   # hardcoded password (funcarg)
    "B107": "CWE-798",   # hardcoded password (default)
    "B108": "CWE-377",   # insecure temp file
    "B110": "CWE-390",   # try/except pass
    "B201": "CWE-94",    # flask debug mode
    "B202": "CWE-94",    # flask with debug
    "B301": "CWE-502",   # pickle unsafely
    "B302": "CWE-502",   # marshal loads
    "B303": "CWE-327",   # MD5/SHA1 use
    "B304": "CWE-327",   # use of weak cipher
    "B305": "CWE-327",   # cipher mode without IV
    "B306": "CWE-377",   # mktemp
    "B307": "CWE-78",    # eval
    "B308": "CWE-79",    # mark_safe XSS
    "B310": "CWE-601",   # urllib open
    "B311": "CWE-330",   # random not for security
    "B312": "CWE-319",   # telnetlib
    "B313": "CWE-611",   # xml minidom
    "B320": "CWE-611",   # xml lxml
    "B321": "CWE-319",   # ftp lib
    "B322": "CWE-78",    # input() python 2
    "B323": "CWE-295",   # unverified context
    "B324": "CWE-327",   # hashlib new MD5
    "B325": "CWE-327",   # hashlib MD4
    "B401": "CWE-319",   # import telnetlib
    "B402": "CWE-319",   # import ftplib
    "B403": "CWE-502",   # import pickle
    "B404": "CWE-78",    # import subprocess
    "B405": "CWE-611",   # import xml.etree
    "B406": "CWE-611",   # import xml.sax
    "B407": "CWE-611",   # import xml.expat
    "B408": "CWE-611",   # import xml.minidom
    "B409": "CWE-611",   # import xml.pulldom
    "B410": "CWE-611",   # import lxml
    "B411": "CWE-319",   # import xmlrpc
    "B412": "CWE-319",   # import httpoxy
    "B413": "CWE-327",   # import pycrypto
    "B501": "CWE-295",   # request with no cert verify
    "B502": "CWE-326",   # ssl with bad version
    "B503": "CWE-295",   # ssl with insecure defaults
    "B504": "CWE-295",   # ssl wrap socket without cert
    "B505": "CWE-326",   # weak RSA key
    "B506": "CWE-20",    # yaml load
    "B507": "CWE-295",   # paramiko no host key verify
    "B601": "CWE-78",    # paramiko exec
    "B602": "CWE-78",    # subprocess with shell=True
    "B603": "CWE-78",    # subprocess without shell
    "B604": "CWE-78",    # function call with shell
    "B605": "CWE-78",    # os.system
    "B606": "CWE-78",    # os.spawn
    "B607": "CWE-78",    # start process with partial path
    "B608": "CWE-89",    # hardcoded SQL
    "B609": "CWE-78",    # wildcard injection
    "B610": "CWE-89",    # django extra SQL
    "B611": "CWE-89",    # django rawsql
    "B701": "CWE-94",    # jinja2 autoescape off
    "B702": "CWE-94",    # mako templates
    "B703": "CWE-79",    # django mark_safe XSS
}

BANDIT_SEVERITY_MAP = {
    "LOW": Severity.LOW,
    "MEDIUM": Severity.MEDIUM,
    "HIGH": Severity.HIGH,
}


class BanditScanner(BaseScanner):
    """
    Bandit SAST scanner for Python code.
    Requires: pip install bandit
    """

    name = "bandit"
    supported_languages = ["python"]

    def _tool_name(self) -> str:
        return "bandit"

    def scan(self) -> list[Vulnerability]:
        """Run bandit and parse JSON output."""
        if not self.is_available():
            print("[BanditScanner] bandit not found. Install with: pip install bandit")
            return []

        returncode, stdout, stderr = self._run_command([
            "bandit",
            "-r", self.repo_path,
            "-f", "json",
            "--quiet",
        ])

        if not stdout:
            return []

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return []

        vulns = []
        for issue in data.get("results", []):
            test_id = issue.get("test_id", "")
            cwe = BANDIT_TO_CWE.get(test_id, f"CWE-unknown-{test_id}")
            severity_str = issue.get("issue_severity", "MEDIUM").upper()
            severity = BANDIT_SEVERITY_MAP.get(severity_str, Severity.MEDIUM)

            vuln = self._make_vuln(
                cwe=cwe,
                file_path=issue.get("filename", "").replace(self.repo_path, "").lstrip("/"),
                line_number=issue.get("line_number"),
                snippet=issue.get("code", "").strip(),
                severity_override=severity,
                description=issue.get("issue_text", ""),
            )
            vulns.append(vuln)

        return vulns
