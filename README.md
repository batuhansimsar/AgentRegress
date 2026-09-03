# AgentRegress

AgentRegress is a research prototype for measuring security regressions introduced during autonomous code repair. A repair succeeds only when the build, functional acceptance tests, and separate dynamic-security acceptance tests all pass.

## Implemented

- A versioned manifest at benchmarks/manifest.yaml with four isolated task repositories: three security-repair tasks and one functional-repair task.
- Separate functional_tests and security_tests for every benchmark. Fixtures are copied to a run directory before an agent can modify them.
- A real Gemini runner using google-genai and GEMINI_API_KEY. Local .env loading is supported and .env is ignored by Git.
- Three distinct RQ6 treatments:
  - baseline: build plus functional-test feedback only;
  - security_aware: dynamic-security tests, scanner findings, and explicit security policy;
  - self_correction: build and functional feedback plus self-review, without scanner/policy feedback.
- A validated structured-patch contract: one JSON object containing complete file replacements. Unauthorized paths, traversal, duplicates, missing files, and invalid Python are rejected before an atomic write.
- Per-state raw evidence: model prompt/response, patch outcome, compiler output, functional/security test outputs, scanner raw output, findings, and Git SHA.
- Fingerprint-based regression metrics, so same-CWE findings in different locations are not collapsed.
- A real-run analysis script that generates CSV, Parquet, bootstrap CIs, effect-size tables, and RQ tables.
- Unit tests for patch application, raw evidence, regression metrics, and prompt-treatment separation.

## Not yet a final study

- Gemini is the sole real-model adapter. RQ5 needs at least one additional model and matched repeated runs before a model-comparison finding is defensible.
- The four-repository benchmark set is an inspectable seed set, not a final external corpus.
- Scanner output is not ground truth. final_secure requires scanner cleanliness and passing dynamic-security tests, but manual validation remains necessary.
- experiments/mock_experiment.py and checked-in dashboard data are synthetic demonstrations, not research findings.

## Setup

~~~bash
cd AgentRegress
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY="..."
~~~

Alternatively, create local .env containing GEMINI_API_KEY. Never commit it.

## Run a real experiment

Validate a task without contacting a model:

~~~bash
python3 run_experiment.py --agent gemini --task A001 --mode baseline --dry-run
~~~

Run one task:

~~~bash
python3 run_experiment.py --agent gemini --model gemini-2.5-flash --task A001 --mode baseline --iterations 5
~~~

Run every task using the security-aware treatment:

~~~bash
python3 run_experiment.py --agent gemini --task all --mode security_aware --iterations 5
~~~

Evidence is written to results/real/<timestamp>/<task-id>/result.json. The working copy lives alongside that file; the source fixture is not changed.

## Analyze real runs

~~~bash
python3 analysis/analyze_runs.py --results-dir results/real --output-dir analysis/output
~~~

The command writes runs.csv, runs.parquet, regression_events.csv, regression_events.parquet, effect_sizes.csv, rq_tables.csv, rq_tables.md, and summary.json. Only artifacts marked data_kind: real are analyzed; mock and dashboard data is excluded.

## Benchmark tasks

Each manifest entry specifies a source repository, source/editable paths, functional and dynamic-security pytest paths, and initial vulnerability IDs. The supplied tasks are:

- A001: SQL injection
- A002: path traversal
- A003: missing authentication
- B001: functional greeting crash

Security tests are behavioral checks independent of static scanners.

## Dashboard and mock data

The mock experiment remains useful for UI development only. The dashboard has a visible synthetic-data label; its values must not be cited as real findings. Analyze real data through analysis/analyze_runs.py or export it to a separately labeled dashboard dataset.

## Safety

Benchmark fixtures contain intentional vulnerabilities. Use them only in an isolated research environment; do not deploy or expose them.
