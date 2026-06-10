# Task: fix the failing tests in widgetlib

The `widgetlib` package (modules `textkit.py`, `numkit.py`, `listkit.py`) has
several bugs that make its test suite fail. Fix the modules so the whole suite
passes.

Rules:
- Run the tests with `python3 -m pytest -q`.
- Fix bugs in the `widgetlib/` modules only.
- Do NOT edit `test_widgetlib.py` — the tests define the required behavior.
- You are done when `python3 -m pytest -q` reports all tests passing.

Work until the suite is green.
