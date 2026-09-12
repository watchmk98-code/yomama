#!/usr/bin/env python3
"""Run the economy tests without installing anything.

    python3 tests/run_tests.py [name-fragment ...]

The repo has no build step and no dependencies, so the tests must run on a
plain Python 3.9. The test file is also valid pytest, if you have it:

    python3 -m pytest tests
"""

from __future__ import annotations

import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import test_economy  # noqa: E402


def main(argv):
    wanted = argv[1:]
    tests = [(n, f) for n, f in sorted(vars(test_economy).items())
             if n.startswith("test_") and callable(f)]
    if wanted:
        tests = [(n, f) for n, f in tests if any(w in n for w in wanted)]

    failed = 0
    for name, fn in tests:
        t0 = time.perf_counter()
        try:
            fn()
            print(f"  ok   {name}  ({time.perf_counter() - t0:.1f}s)")
        except Exception:
            failed += 1
            print(f"  FAIL {name}  ({time.perf_counter() - t0:.1f}s)")
            traceback.print_exc()
    total = len(tests)
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
