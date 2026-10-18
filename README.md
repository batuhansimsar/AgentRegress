# AgentRegress — Simple Code Repair Evaluator

A small Python learning project that **evaluates a proposed bug fix**. It does not generate fixes automatically.

## How it works

1. Run tests against the original code.
2. Run the same tests against the proposed fix.
3. Check the fixed code for direct `eval()` / `exec()` calls.
4. Save the results in `report.json`.

## Demo (Python 3.10+)

```bash
python agentregress.py --original examples/buggy.py --patch examples/fixed.py --tests examples/check_divide.py
```

Expected: `baseline_passed: false`, `patch_passed: true`, `accepted: true`. A `report.json` file is created.

Run project tests:

```bash
python -m unittest discover -s tests -v
```

No external dependencies.

## Project layout

- `agentregress.py` — main evaluator and CLI
- `examples/buggy.py` — original code with a bug
- `examples/fixed.py` — proposed fix
- `examples/check_divide.py` — checks for correct output
- `tests/test_agentregress.py` — project unit tests

## What to say in a presentation

> AgentRegress is a simple tool for checking whether a proposed Python code change fixes a bug. It runs the same tests before and after the change, performs two basic security checks, and produces a JSON report. In the example, multiplication was mistakenly used instead of division; the corrected version passes both tests.

## Important limitations

**Only run trusted test scripts and patches.** The tool starts Python subprocesses, but these are **not** an isolated security sandbox. `-I` is Python's isolated interpreter mode, not OS/container isolation. The AST check catches only direct `eval()` and `exec()` calls and is not comprehensive security scanning. This is a beginner-friendly evaluation prototype, not an autonomous repair agent or production security tool.
