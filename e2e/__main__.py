import sys
import unittest

from .harness import E2E_ROOT

if __name__ == "__main__":
  names = [
    f"{__package__}.{path.stem}"
    for path in sorted(E2E_ROOT.glob("e2e_*.py"))
  ]
  suite = unittest.defaultTestLoader.loadTestsFromNames(names)
  result = unittest.TextTestRunner(verbosity=2).run(suite)
  sys.exit(0 if result.wasSuccessful() else 1)
