The test suite `test_speclib.py` is failing. Fix the bugs in the `mod00.py` …
`mod23.py` modules until `python3 -m pytest -q` passes.

Each module defines ONE function with a buggy body. The correct behavior for that
function is stated **only** in the module's **BEHAVIOR REFERENCE** docstring at the
top of the file — you must read it, because the test pins each function's outputs
with a one-way digest and therefore contains no expected values to copy. Every
module implements different logic with its own constants, so each fix requires
reading that module's reference.

Do **not** edit `test_speclib.py` (it defines the expected behavior).

Work through all 24 modules until the whole suite is green.
