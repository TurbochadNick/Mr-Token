# Task: fix the event classifier from noisy diagnostics

Fix `processor.py` so the full test suite passes.

Rules:
- You may edit `processor.py` only.
- Do not edit `test_processor.py` or `build_check.py`.
- The diagnostic command is intentionally noisy:

  ```bash
  python3 build_check.py
  ```

- If MR Token warns that a large output is sitting in context, follow the assigned
  arm:
  - `ignore`: continue without using offload.
  - `follow_offload`: use MR Token's offload guidance, keep only a compact summary
    or targeted query in context, then continue.
- Verify with:

  ```bash
  python3 -m unittest -q
  ```

You are done when the oracle passes.
