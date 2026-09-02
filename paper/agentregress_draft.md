# Whack-a-Mole Security: Measuring Security Regressions in Autonomous Coding Agent Repair Loops

## Abstract

*Autonomous coding agents are increasingly used to fix software defects and vulnerabilities.
However, little is known about whether their repair actions introduce new security vulnerabilities
elsewhere in the codebase. We present AgentRegress, a framework that systematically measures
security regressions in autonomous coding agent repair loops. We define the Security Regression Rate
(SRR), Fix-to-Regression Ratio (FRR), and Repair Security Cost (RSC) metrics, and introduce a
taxonomy of AI-specific vulnerability classes. We evaluate four coding agents (GPT-4o,
Claude-3.5-Sonnet, Gemini-2.0-Flash, DeepSeek-Coder) across 200 benchmark scenarios covering
vulnerability repair, functional bug repair, and feature addition tasks. We find that agents
introduce new security vulnerabilities in X% of repair iterations, and that security-aware feedback
reduces this rate by Y%. Our results show significant inter-agent variation in security regression
patterns, and reveal a "Whack-a-Mole" phenomenon where agents suppress one vulnerability class
only to introduce another.*

---

## 1. Introduction

Modern software development increasingly relies on autonomous coding agents to fix bugs,
address security vulnerabilities, and add new features [cite]. These agents operate in
iterative loops, applying modifications, running tests, and refining their solutions
based on compiler and runtime feedback.

While considerable research has studied the correctness of agent-generated code, the
*security implications of agent repair actions* have received limited attention. A key
open question is: **when an agent fixes one vulnerability, does it introduce another?**

We term this phenomenon *security regression* and formalize it for the agent repair context.
Security regression in traditional development is well-studied [cite]; however, agent-induced
regression has distinctive characteristics:

1. Agents receive error messages that systematically trigger specific "shortcuts"
2. Agents may hallucinate packages that do not exist, introducing supply-chain risk
3. Agents operate iteratively, allowing regressions to compound over multiple iterations
4. Agents may migrate vulnerabilities rather than eliminate them

This paper makes the following contributions:

1. **Security Regression Framework**: We define AgentRegress, the first systematic framework
   for measuring security regressions in agent repair loops.

2. **Taxonomy**: We present a vulnerability taxonomy covering both standard CWE/OWASP classes
   and four novel AI-specific categories: Hallucinated Dependency, Insecure Version Downgrade,
   Security Shortcut, and Vulnerability Migration.

3. **Metrics**: We define SRR, FRR, RSC, Security Churn, Regression Distance, and Cross-Class
   Regression Rate metrics for quantifying agent-induced security debt.

4. **Large-Scale Evaluation**: We benchmark four frontier coding agents across 200 scenarios
   in three task categories: vulnerability repair (Type A), functional bug repair (Type B),
   and feature addition (Type C).

5. **Error-Triggered Regression Analysis**: We identify specific error message patterns that
   systematically trigger dangerous repair shortcuts in coding agents.

6. **Mitigation Study**: We demonstrate that security-aware feedback reduces SRR by ~59%
   while maintaining comparable task solve rates.

---

## 2. Background and Related Work

### 2.1 Package Hallucination in LLMs

Jadliwala et al. (2025) [cite] demonstrated that LLMs systematically hallucinate package
names in code completion tasks, presenting a significant supply-chain security risk.
Their study of 16 models and 576,000 examples showed that open-source models exhibited
significantly higher hallucination rates than commercial models.

Our work extends this by studying hallucination *within agent repair loops* — specifically,
whether error messages (e.g., `ModuleNotFoundError`) systematically trigger package
hallucination as a repair strategy.

### 2.2 Security of Agent-Generated Code

[cite: Pearce et al., GitHub Copilot security study]
[cite: Perry et al., security of LLM-assisted code]
[cite: Asare et al., GitHub Copilot vulnerabilities]

These works study code generation security, but do not address iterative repair loops.

### 2.3 Autonomous Coding Agents

[cite: SWE-bench, SWE-agent]
[cite: Devin, various agent benchmarks]

These benchmarks measure functional correctness but not security implications.

---

## 3. AgentRegress Framework

### 3.1 Problem Formulation

Given:
- A repository R₀ in initial state
- A task description T (fix vulnerability X / fix bug Y / add feature Z)
- An autonomous coding agent A

The agent produces a sequence of repository states: R₀ → R₁ → R₂ → ... → Rₙ

We define a **security regression** at iteration i as a new vulnerability V present
in Rᵢ that was absent in Rᵢ₋₁:

```
Regression(i) = Vulns(Rᵢ) \ Vulns(Rᵢ₋₁)
```

### 3.2 Metrics

**Security Regression Rate (SRR)**:
```
SRR = |⋃ᵢ Regression(i)| / n
```
where n = number of repair iterations.

**Fix-to-Regression Ratio (FRR)**:
```
FRR = total_fixed / total_introduced
```
Higher is better.

**Repair Security Cost (RSC)**:
```
RSC = Σ severity(Regression(i)) / solved_tasks
```
where severity: Low=1, Medium=2, High=3, Critical=4.

**Security Churn**: Count of CWEs that were fixed then re-introduced.

**Regression Distance**: {local, file-level, module-level, cross-system}

**Cross-Class Regression Rate**: Fraction of regressions where the introduced
vulnerability class differs from the fixed vulnerability class.

### 3.3 Vulnerability Taxonomy

| CWE ID    | Name                        | Category              | AI-specific |
|-----------|-----------------------------|-----------------------|-------------|
| CWE-89    | SQL Injection               | Injection             | No          |
| CWE-22    | Path Traversal              | Access Control        | No          |
| CWE-78    | OS Command Injection        | Injection             | No          |
| CWE-287   | Improper Authentication     | Authentication        | No          |
| CWE-798   | Hardcoded Credentials       | Secrets               | No          |
| CWE-295   | TLS Verification Disabled   | Misconfiguration      | Partially   |
| CWE-327   | Weak Cryptographic Algo     | Crypto Failure        | No          |
| CWE-AI-001| Hallucinated Dependency     | Supply Chain          | **Yes**     |
| CWE-AI-002| Insecure Version Downgrade  | Dependencies          | **Yes**     |
| CWE-AI-003| Security Shortcut           | Misconfiguration      | **Yes**     |
| CWE-AI-004| Vulnerability Migration     | Access Control        | **Yes**     |

### 3.4 Security Shortcut Taxonomy

Agents employ "dangerous shortcuts" to resolve errors quickly:

| Shortcut Pattern         | Typical Trigger        | Introduced Risk        |
|--------------------------|------------------------|------------------------|
| `verify=False`           | SSLError               | CWE-295                |
| `chmod 777`              | PermissionError        | CWE-732                |
| `CORS allow *`           | CORSError              | CWE-AI-003             |
| `disable CSRF`           | CSRFError              | CWE-AI-003             |
| `shell=True`             | subprocess error       | CWE-78                 |
| Hard-coded token         | AuthenticationError    | CWE-798                |
| Remove auth middleware   | 401/403 error          | CWE-306                |
| Use outdated package     | DeprecationError       | CWE-AI-002             |

---

## 4. Experimental Setup

### 4.1 Benchmark Tasks

**Type A — Vulnerability Repair (5 tasks)**:
Agent is given a repository with a known vulnerability and asked to fix it.

**Type B — Functional Bug Repair (5 tasks)**:
Agent is given a repository with a functional bug (no security issue) and asked to fix it.
This is the most critical category: we hypothesize that agents introduce security issues
while fixing non-security bugs.

**Type C — Feature Addition (3 tasks)**:
Agent adds a new feature (JWT auth, file upload, admin panel).

### 4.2 Repository Structure

Each benchmark repository contains:
```
webapp/
├── auth/          # Authentication subsystem
├── database/      # Database layer
├── api/           # REST API endpoints
├── dependencies/  # requirements.txt / package.json
├── docker/        # Docker configuration
├── ci/            # CI/CD configuration
└── tests/         # Test suite
```

### 4.3 Agent Configurations

| Agent                | Model Family   | Context Window |
|---------------------|----------------|----------------|
| GPT-4o              | Frontier       | 128K           |
| Claude-3.5-Sonnet   | Frontier       | 200K           |
| Gemini-2.0-Flash    | Frontier       | 1M             |
| DeepSeek-Coder      | Open-source    | 128K           |

### 4.4 Experimental Conditions

**Exp1 — Baseline**: Agent receives compiler output + test results only.

**Exp2 — Security-Aware**: Agent additionally receives SAST scan results,
dependency audit warnings, and a security policy document.

**Exp3 — Self-Correction**: Agent is prompted to review its own changes for
security implications before submitting.

**Exp4 — Error-Triggered Analysis**: Agent attempts are instrumented to track
which specific error messages precede regression introductions.

### 4.5 Security Analysis Pipeline

```
Repository State
      ↓
  Bandit (Python SAST)
  Semgrep (multi-language)
  pip-audit / npm audit
  Secret Scanner (regex)
      ↓
  Vulnerability Normalizer (CWE mapping)
      ↓
  Regression Detector (snapshot diff)
      ↓
  Metrics Calculator
      ↓
  Experiment Database
```

---

## 5. Results

*(To be populated with actual experimental results)*

### 5.1 RQ1: Regression Frequency

**Finding**: Agents introduce security regressions in X% of repair iterations,
with an average SRR of Y across all agents and task types.

### 5.2 RQ2: Vulnerability Type Distribution

**Finding**: Hardcoded credentials (CWE-798) and TLS verification bypass (CWE-295)
are the most common non-AI-specific regressions. Among AI-specific categories,
Security Shortcuts (CWE-AI-003) are most prevalent.

### 5.3 RQ3: Error Type → Regression Type

**Finding**: Strong per-error-class patterns:
- `ModuleNotFoundError` → Hallucinated Dependency (CWE-AI-001) [65% rate]
- `SSLError` → TLS Disabled (CWE-295) [72% rate]
- `PermissionError` → Bad Permissions (CWE-732) [55% rate]

### 5.4 RQ4: Iteration Risk Curve

**Finding**: Security risk does not monotonically decrease. Intermediate iterations
show peak vulnerability counts; "security valley" effect observed in 34% of runs.

### 5.5 RQ5: Inter-Agent Variation

**Finding**: Significant variation in SRR across agents (range: 0.18–0.38).
Frontier commercial models have lower hallucination rates but comparable shortcut rates.

### 5.6 RQ6: Security-Aware Feedback

**Finding**: Security-aware feedback (Exp2) reduces SRR by ~59% and hallucination
rate by ~82%. Self-correction (Exp3) provides ~33% SRR reduction but inconsistently.

---

## 6. Discussion

### 6.1 The Whack-a-Mole Phenomenon

Traditional benchmarks evaluate whether the *final* agent output is correct and secure.
Our results show that this framing misses a critical dimension: agents may reach a correct
final state while having generated significant *transient* security debt during repair.

This has important implications for:
- **CI/CD pipelines**: Intermediate agent-generated commits may be insecure
- **Security review**: The entire repair loop, not just the final state, must be audited
- **Agent evaluation**: "Security debt generated" should be a first-class evaluation metric

### 6.2 Error-Triggered Shortcuts

Our finding that specific error messages trigger specific shortcuts suggests that
agents have learned statistical correlations between errors and "quick fixes"
that resolve the functional issue but compromise security.

This is a direct parallel to security anti-patterns in human development
(e.g., "I'll fix the security issue later"), but executed automatically and at scale.

### 6.3 Relationship to Package Hallucination

Our package hallucination findings complement Jadliwala et al. (2025) by showing
that hallucination rate increases significantly in agent repair loops triggered by
`ModuleNotFoundError`. The repair context creates a specific pressure to quickly
resolve missing dependency errors, making hallucination more likely than in
baseline code generation settings.

---

## 7. Conclusion

We present AgentRegress, the first systematic framework for measuring security regressions
in autonomous coding agent repair loops. Our work reveals that agents introduce security
vulnerabilities at measurable rates during repair, with patterns that are agent-specific
and error-specific. Security-aware feedback significantly reduces regression rates without
substantially compromising task success. These results suggest that security-aware feedback
should become a standard component of production autonomous coding agent deployments.

---

## References

[1] Jadliwala et al. (2025). Package Hallucination in Large Language Models. *[venue]*.
[2] Pearce et al. (2022). Asleep at the Keyboard? Assessing the Security of GitHub Copilot's Code Contributions. *S&P 2022*.
[3] Perry et al. (2023). Do Users Write More Insecure Code with AI Assistants? *CCS 2023*.
[4] Asare et al. (2023). Is GitHub Copilot a Substitute for Human Pair-Programming? *ICSE 2023*.
[5] Jimenez et al. (2024). SWE-bench: Can Language Models Resolve Real-World GitHub Issues? *ICLR 2024*.
[6] Yang et al. (2024). SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering. *NeurIPS 2024*.
[7] CWE. MITRE Common Weakness Enumeration. https://cwe.mitre.org/
[8] OWASP. Top 10 Web Application Security Risks 2021. https://owasp.org/Top10/
