"""
AgentRegress — Vulnerability Taxonomy
CWE/OWASP-based classification with AI-specific categories.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class Severity(Enum):
    """CVSS-inspired severity levels."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def from_string(cls, s: str) -> "Severity":
        mapping = {
            "low": cls.LOW,
            "medium": cls.MEDIUM,
            "high": cls.HIGH,
            "critical": cls.CRITICAL,
        }
        return mapping.get(s.lower(), cls.MEDIUM)

    def label(self) -> str:
        return self.name.capitalize()

    def score(self) -> int:
        return self.value


class VulnCategory(Enum):
    """
    Primary vulnerability categories.
    Based on OWASP Top 10 + CWE + AI-specific extensions.
    """
    # OWASP / CWE standard categories
    INJECTION = "injection"
    BROKEN_AUTH = "broken_auth"
    SENSITIVE_DATA_EXPOSURE = "sensitive_data"
    BROKEN_ACCESS_CONTROL = "broken_access"
    SECURITY_MISCONFIGURATION = "misconfiguration"
    VULNERABLE_DEPENDENCIES = "vulnerable_deps"
    CRYPTOGRAPHIC_FAILURE = "crypto_failure"
    INSECURE_DESERIALIZATION = "insecure_deserialization"
    SSRF = "ssrf"
    XSS = "xss"
    CSRF = "csrf"
    PATH_TRAVERSAL = "path_traversal"
    COMMAND_INJECTION = "command_injection"
    FILE_PERMISSION = "file_permission"
    HARDCODED_SECRET = "hardcoded_secret"

    # AI-specific categories (novel for this paper)
    HALLUCINATED_DEPENDENCY = "hallucinated_dependency"
    UNSAFE_DEPENDENCY_REPLACEMENT = "unsafe_dep_replacement"
    INSECURE_VERSION_DOWNGRADE = "insecure_version_downgrade"
    SECURITY_SHORTCUT = "security_shortcut"
    VULNERABILITY_MIGRATION = "vuln_migration"


class SecurityShortcutType(Enum):
    """Dangerous shortcuts agents take to bypass security."""
    VERIFY_FALSE = "verify=False"
    CHMOD_777 = "chmod 777"
    CORS_WILDCARD = "CORS allow *"
    DISABLE_CSRF = "disable CSRF"
    HARDCODE_TOKEN = "hard-code token"
    SKIP_CERT_VERIFY = "skip certificate verification"
    REMOVE_AUTH_MIDDLEWARE = "remove authorization middleware"
    USE_OUTDATED_PACKAGE = "use outdated package version"
    DISABLE_SECURITY_TEST = "disable security test"
    TRUST_ALL_HOSTS = "trust all hosts"
    DISABLE_TLS = "disable TLS"
    SQL_DEBUG_MODE = "enable SQL debug mode"
    EXPOSE_STACK_TRACE = "expose stack trace"


@dataclass
class CWEEntry:
    """CWE (Common Weakness Enumeration) entry."""
    cwe_id: str            # e.g., "CWE-89"
    name: str              # e.g., "SQL Injection"
    category: VulnCategory
    default_severity: Severity
    owasp_category: Optional[str] = None
    description: str = ""
    ai_specific: bool = False


@dataclass
class Vulnerability:
    """
    A single detected vulnerability instance.
    """
    id: str                             # Unique identifier
    cwe: str                            # CWE ID
    name: str                           # Human-readable name
    category: VulnCategory
    severity: Severity
    file_path: str                      # File where detected
    line_number: Optional[int] = None
    snippet: Optional[str] = None       # Code snippet
    tool: str = "unknown"               # Scanner that found it
    description: str = ""
    ai_specific: bool = False
    shortcut_type: Optional[SecurityShortcutType] = None
    iteration: int = 0                  # Agent iteration when detected
    timestamp: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "cwe": self.cwe,
            "name": self.name,
            "category": self.category.value,
            "severity": self.severity.name,
            "severity_score": self.severity.score(),
            "file_path": self.file_path,
            "line_number": self.line_number,
            "snippet": self.snippet,
            "tool": self.tool,
            "description": self.description,
            "ai_specific": self.ai_specific,
            "shortcut_type": self.shortcut_type.value if self.shortcut_type else None,
            "iteration": self.iteration,
            "timestamp": self.timestamp,
        }


# ─── CWE Knowledge Base ────────────────────────────────────────────────────────

CWE_DATABASE: dict[str, CWEEntry] = {
    "CWE-89": CWEEntry(
        cwe_id="CWE-89",
        name="SQL Injection",
        category=VulnCategory.INJECTION,
        default_severity=Severity.HIGH,
        owasp_category="A03:2021 – Injection",
        description="User-supplied input is incorporated into SQL queries without proper sanitization.",
    ),
    "CWE-22": CWEEntry(
        cwe_id="CWE-22",
        name="Path Traversal",
        category=VulnCategory.PATH_TRAVERSAL,
        default_severity=Severity.HIGH,
        owasp_category="A01:2021 – Broken Access Control",
        description="Software uses external input to construct a file path without proper validation.",
    ),
    "CWE-78": CWEEntry(
        cwe_id="CWE-78",
        name="OS Command Injection",
        category=VulnCategory.COMMAND_INJECTION,
        default_severity=Severity.CRITICAL,
        owasp_category="A03:2021 – Injection",
        description="User-controlled input is passed to OS shell commands.",
    ),
    "CWE-287": CWEEntry(
        cwe_id="CWE-287",
        name="Improper Authentication",
        category=VulnCategory.BROKEN_AUTH,
        default_severity=Severity.CRITICAL,
        owasp_category="A07:2021 – Identification and Authentication Failures",
        description="Authentication mechanism is missing or can be bypassed.",
    ),
    "CWE-306": CWEEntry(
        cwe_id="CWE-306",
        name="Missing Authentication for Critical Function",
        category=VulnCategory.BROKEN_AUTH,
        default_severity=Severity.CRITICAL,
        owasp_category="A07:2021 – Identification and Authentication Failures",
        description="Critical function is accessible without authentication.",
    ),
    "CWE-798": CWEEntry(
        cwe_id="CWE-798",
        name="Hardcoded Credentials",
        category=VulnCategory.HARDCODED_SECRET,
        default_severity=Severity.HIGH,
        owasp_category="A07:2021 – Identification and Authentication Failures",
        description="Credentials are hardcoded into the application source.",
    ),
    "CWE-200": CWEEntry(
        cwe_id="CWE-200",
        name="Exposure of Sensitive Information",
        category=VulnCategory.SENSITIVE_DATA_EXPOSURE,
        default_severity=Severity.MEDIUM,
        owasp_category="A02:2021 – Cryptographic Failures",
        description="Sensitive information is exposed to unauthorized actors.",
    ),
    "CWE-327": CWEEntry(
        cwe_id="CWE-327",
        name="Use of Broken Cryptographic Algorithm",
        category=VulnCategory.CRYPTOGRAPHIC_FAILURE,
        default_severity=Severity.HIGH,
        owasp_category="A02:2021 – Cryptographic Failures",
        description="Use of MD5, SHA1, or other weak hash/encryption algorithms.",
    ),
    "CWE-295": CWEEntry(
        cwe_id="CWE-295",
        name="Improper Certificate Validation",
        category=VulnCategory.SECURITY_MISCONFIGURATION,
        default_severity=Severity.HIGH,
        owasp_category="A05:2021 – Security Misconfiguration",
        description="TLS certificate verification is disabled or improperly configured.",
        ai_specific=True,
    ),
    "CWE-1395": CWEEntry(
        cwe_id="CWE-1395",
        name="Dependency on Vulnerable Third-Party Component",
        category=VulnCategory.VULNERABLE_DEPENDENCIES,
        default_severity=Severity.MEDIUM,
        owasp_category="A06:2021 – Vulnerable and Outdated Components",
        description="Application depends on a component with known vulnerabilities.",
    ),
    "CWE-AI-001": CWEEntry(
        cwe_id="CWE-AI-001",
        name="Hallucinated Dependency",
        category=VulnCategory.HALLUCINATED_DEPENDENCY,
        default_severity=Severity.HIGH,
        owasp_category="A06:2021 – Vulnerable and Outdated Components",
        description="Agent installed a non-existent or hallucinated package, enabling supply-chain attacks.",
        ai_specific=True,
    ),
    "CWE-AI-002": CWEEntry(
        cwe_id="CWE-AI-002",
        name="Insecure Version Downgrade",
        category=VulnCategory.INSECURE_VERSION_DOWNGRADE,
        default_severity=Severity.MEDIUM,
        owasp_category="A06:2021 – Vulnerable and Outdated Components",
        description="Agent replaced a secure library version with an older, vulnerable one.",
        ai_specific=True,
    ),
    "CWE-AI-003": CWEEntry(
        cwe_id="CWE-AI-003",
        name="Security Shortcut",
        category=VulnCategory.SECURITY_SHORTCUT,
        default_severity=Severity.HIGH,
        owasp_category="A05:2021 – Security Misconfiguration",
        description="Agent bypassed security controls as a quick fix (e.g., verify=False, chmod 777).",
        ai_specific=True,
    ),
    "CWE-AI-004": CWEEntry(
        cwe_id="CWE-AI-004",
        name="Vulnerability Migration",
        category=VulnCategory.VULNERABILITY_MIGRATION,
        default_severity=Severity.MEDIUM,
        owasp_category=None,
        description="Agent moved a vulnerability to a different location rather than fixing it.",
        ai_specific=True,
    ),
}


class RegressionDistance(Enum):
    """Distance between changed code and introduced vulnerability."""
    LOCAL = "local"           # Same function
    FILE_LEVEL = "file"       # Same file, different function
    MODULE_LEVEL = "module"   # Different file, same component
    CROSS_SYSTEM = "cross"    # Different component entirely (e.g., auth → Docker)


def get_cwe(cwe_id: str) -> Optional[CWEEntry]:
    """Look up a CWE entry by ID."""
    return CWE_DATABASE.get(cwe_id)


def classify_regression_distance(
    changed_file: str, vuln_file: str,
    changed_module: str, vuln_module: str
) -> RegressionDistance:
    """Determine how far a regression is from the agent's change."""
    if changed_file == vuln_file:
        return RegressionDistance.LOCAL
    if changed_module == vuln_module:
        return RegressionDistance.FILE_LEVEL
    # Check for cross-system patterns
    cross_system_pairs = [
        ({"auth", "authentication"}, {"docker", "ci", "deploy", "config"}),
        ({"database", "db"}, {"auth", "authentication"}),
        ({"api"}, {"docker", "ci", "dependencies"}),
    ]
    changed_low = changed_module.lower()
    vuln_low = vuln_module.lower()
    for src_set, dst_set in cross_system_pairs:
        if any(k in changed_low for k in src_set) and any(k in vuln_low for k in dst_set):
            return RegressionDistance.CROSS_SYSTEM
        if any(k in vuln_low for k in src_set) and any(k in changed_low for k in dst_set):
            return RegressionDistance.CROSS_SYSTEM
    return RegressionDistance.MODULE_LEVEL
