"""AgentRegress: evaluate a proposed Python fix using tests and simple checks."""
import argparse
import ast
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DANGEROUS_CALLS = {'eval', 'exec'}


def security_check(source):
    """Flag direct eval/exec calls. This is a small demo, not a security audit."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ['Invalid Python syntax']
    return [f'Line {n.lineno}: avoid {n.func.id}()'
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in DANGEROUS_CALLS]


def test_code(file_path, test_path):
    """Run a test script with the code file as its first argument."""
    try:
        result = subprocess.run(
            [sys.executable, '-I', str(test_path.resolve()), str(file_path.resolve())],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return {'passed': result.returncode == 0,
                'output': (result.stdout + result.stderr)[-2000:]}
    except subprocess.TimeoutExpired:
        return {'passed': False, 'output': 'Test timed out after 10 seconds'}


def evaluate(original, patch, tests, report):
    before = test_code(original, tests)
    after = test_code(patch, tests)
    warnings = security_check(patch.read_text(encoding='utf-8'))
    result = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'baseline_passed': before['passed'],
        'patch_passed': after['passed'],
        'security_warnings': warnings,
        'accepted': after['passed'] and not warnings,
        'baseline_output': before['output'],
        'patch_output': after['output'],
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description='Evaluate a proposed Python code fix')
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--patch', type=Path, required=True)
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--report', type=Path, default=Path('report.json'))
    args = parser.parse_args()
    result = evaluate(args.original, args.patch, args.tests, args.report)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['accepted'] else 1)


if __name__ == '__main__':
    main()
