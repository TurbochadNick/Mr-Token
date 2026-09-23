#!/usr/bin/env python3
"""MR Token — UserPromptSubmit hook: SILENT by policy.

It fires when the user presses Enter, i.e. at INITIATION, the one moment the
numbers cannot have changed since the persistent statusLine last showed them. It
used to inject a status-line copy (an inferior one: no stdin, so no effort, window
or limit, and a raw model id) and, via mrtoken.intervene, a proc-engine
intervention (which also wrote debounce state). Both are gone: Claude's statusLine
is its one readout, and event surfaces fire at completion (Stop, PreCompact), never
at initiation. The intervention engine is silenced here, not deleted; it is carded
separately for its own evidence before anyone revives or removes it.

Kept registered so the settings.json wiring needs no change.
"""
import json, os, sys

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


def main():
    sys.stdin.read()  # drain the payload; nothing is emitted, nothing is written
    sys.exit(0)


if __name__ == "__main__":
    main()
