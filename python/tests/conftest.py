"""Make ``pupiltree_latex`` importable when pytest runs from any directory
(the package is not required to be pip-installed to run its own tests)."""

import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))
