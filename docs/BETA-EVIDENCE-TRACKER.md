# MR Token beta evidence tracker

Use this to collect evidence from the `0.5.5` beta loop. One row per tester.

## Build

- Version: `0.5.5`
- Code commit: `59414f7 Improve Codex HUD and beta cleanup`
- Release tip: current `main` after the beta tester note commit
- Primary surface: Python backend/HUD through `mrtoken-transcript`
- Secondary surface: Codex Stop-hook HUD and central Codex DB

## Tester Rows

| Tester | Dates | Agent | Export received | Rules fired | Cost/cache shape | HUD changed behavior? | Noise/confusion | Keep installed? | Follow-up |
|---|---|---|---|---|---|---|---|---|---|
| 1 |  | Claude / Codex | no |  |  |  |  |  |  |
| 2 |  | Claude / Codex | no |  |  |  |  |  |  |
| 3 |  | Claude / Codex | no |  |  |  |  |  |  |

## Decision Gate

Widen the beta only if:

- at least two testers send redacted exports;
- rules fire on real non-Zach sessions;
- at least one tester reports the HUD changed an actual session decision;
- no tester reports the Codex or Claude HUD as noisy enough to ignore.

If those do not hold, tune recommendation quality before adding features.
