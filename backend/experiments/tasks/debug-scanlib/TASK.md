This library ships extensive design notes in the `notes/` directory. **First read all
of the note files in `notes/` (note00.md … note11.md)** to understand the project's
conventions and history before you change anything.

Then fix the bugs: `test_scanlib.py` is failing. Each of `mod00.py` … `mod23.py`
defines ONE function with a buggy body. The correct behavior for that function is
stated in that module's **BEHAVIOR REFERENCE** docstring at the top of the file (the
test pins outputs with a one-way digest, so there are no expected values to copy).
Fix each module until `python3 -m pytest -q` passes.

Do **not** edit `test_scanlib.py` (it defines the expected behavior).
