import tempfile
import unittest
from pathlib import Path
from agentregress import security_check, evaluate

ROOT = Path(__file__).resolve().parents[1]


class EvaluatorTests(unittest.TestCase):
    def test_safe_code(self):
        self.assertEqual(security_check('print(1)'), [])

    def test_unsafe_code(self):
        self.assertTrue(security_check('eval("1+1")'))

    def test_example_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = evaluate(ROOT / 'examples/buggy.py',
                              ROOT / 'examples/fixed.py',
                              ROOT / 'examples/check_divide.py',
                              Path(tmp) / 'report.json')
            self.assertFalse(result['baseline_passed'])
            self.assertTrue(result['accepted'])
            self.assertTrue((Path(tmp) / 'report.json').exists())


if __name__ == '__main__':
    unittest.main()
