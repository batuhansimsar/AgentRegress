"""Test the code file given as a CLI argument."""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location('candidate', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.divide(10, 2) == 5
assert module.divide(9, 3) == 3
print('Both division tests passed')
