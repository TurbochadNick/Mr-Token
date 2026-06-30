# MR Token beta evidence tracker

Use this to collect evidence from the `0.5.8` beta loop. One row per tester.

## Build

- Version: `0.5.8`
- Baseline code commit: `v0.5.8` tag
- Release tip: current `main` once `v0.5.8` is tagged
- Primary surface: Python backend/HUD through `mrtoken-transcript`
- Secondary surface: Codex Stop-hook HUD and central Codex DB
- Maintainer intake: `mrtoken-transcript beta-summary <export.json> <doctor-bundle.json>`
- Release gates: `./scripts/accept-codex-hud.sh`,
  `./scripts/accept-install-lifecycle.sh`, and
  `./scripts/check-recommendation-quality.sh --db <scratch-codex.db> --refresh-rules`

## Tester Rows

| Tester | Dates | Agent | Export received | Doctor bundle | Rules fired | Cost/cache shape | HUD changed behavior? | Feedback labels | Noise/confusion | Keep installed? | Follow-up |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 |  | Claude / Codex | no | no |  |  |  |  |  |  |  |
| 2 |  | Claude / Codex | no | no |  |  |  |  |  |  |  |
| 3 |  | Claude / Codex | no | no |  |  |  |  |  |  |  |

## Decision Gate

Widen the beta only if:

- at least two testers send redacted exports;
- rules fire on real non-Zach sessions;
- at least one tester reports the HUD changed an actual session decision;
- no tester reports the Codex or Claude HUD as noisy enough to ignore.

If those do not hold, tune recommendation quality before adding features.
