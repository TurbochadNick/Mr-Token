# MR Token beta-tester loop

The lightweight way to get real signal from a tester without a full interview.
Pairs with [USER-INTERVIEW.md](../USER-INTERVIEW.md) (the deep version) and
[INTERVIEW-KIT.md](../INTERVIEW-KIT.md) (recruiting). Use this when someone will
try the tool but not sit for 30 minutes.

The whole loop: **install, use for a few days, send back one redacted file plus
three answers.** Nothing leaves their machine unless they choose to send it.

## Tester package path

Send testers through one path only: the Python backend/HUD.

```bash
git clone <repo-url> mr_token
cd mr_token
./install.sh
mrtoken-transcript doctor
```

Expected result:

- `install.sh` installs `mrtoken-transcript`, runs `init`, and writes Claude Code
  hooks/statusLine plus `/mr-*` skills.
- If `~/.codex/` exists, `init` also installs the Codex skills and Stop hook.
- `mrtoken-transcript doctor` verifies the command, DB, hooks, skills, Codex
  setup, and release tag. If it fails, run `mrtoken-transcript doctor --fix`.

Print the current paste-ready outreach text from the repo:

```bash
mrtoken-transcript beta-note
```

Do not route beta testers through the TypeScript UI unless they are explicitly
testing dashboard work. The beta claim is the live terminal HUD and transcript
backend, not the dashboard.

Maintainer release check before sending a new build:

```bash
./scripts/accept-codex-hud.sh
```

### Codex testers

Codex is a secondary beta path. After install, use Codex normally and look for a
compact Stop-hook line like:

```text
mr · codex gpt-5.5 · ctx 28% · ~681k tok · cache 96% · code · long session: /mr-handoff at phase boundary
```

Inspect aggregate Codex data with:

```bash
mrtoken-transcript fleet --codex
mrtoken-transcript why --codex <session-prefix>
```

Turn everything off with:

```bash
mrtoken-transcript uninstall
```

## What you ask the tester to do

1. **Install + set up** per [QUICKSTART.md](QUICKSTART.md). Use Claude Code in a
   terminal so the ambient HUD shows.
2. **Use it normally for ~3 to 5 days.** No special behavior; the point is to see
   whether the live signals are useful in their real work.
3. **Send back a redacted metrics file:**

   ```bash
   mrtoken-transcript export --redact > mrtoken-beta.json
   mrtoken-transcript doctor --bundle
   ```

   Then email/DM those files. `--redact` drops the only work-revealing fields
   (project paths and session titles). What it contains: per-session token
   counts, cache ratios, cost estimates, profile, tool-call/error counts, and
   which rules fired. What it does NOT contain: prompts, source, file paths,
   titles, commands, or any raw transcript content. The doctor bundle contains
   redacted install checks and no settings contents. They can open both JSON
   files and confirm before sending.

4. **Answer three questions** (2 minutes, in their own words):
   - Did the HUD ever change what you actually did in a session (compact early,
     hand off, stop a retry loop)? Tell me about the last time it did, or that it
     never did.
   - Was anything confusing, noisy, or easy to ignore?
   - Would you keep it installed? If you already turned it off, what made you?

While the beta is running, ask testers to mark useful/noisy nudges when they can:

```bash
mrtoken-transcript feedback <session-prefix> <rule> right|wrong|unsure --note "short note"
```

## What you learn from it

- **From the redacted file:** do the rules fire on *someone else's* fleet the way
  they fire on ours? Which rules, how often, what profiles, what cost shape. This
  is the first evidence the engine generalizes beyond your own machine.
- **From the three answers:** whether the live signal is actually act-on-able for
  them (the wedge), and the first read on retention.

## Privacy note to give the tester verbatim

> MR Token is local-first. It stores only metadata (token counts, hashes, sizes,
> timings, cost estimates) in a folder inside your project, never your prompts or
> source. Nothing is sent anywhere automatically. The only thing that leaves your
> machine is the file you choose to send, and `--redact` strips project paths and
> titles from even that.

## Logging what comes back

Keep a row per tester (reuse the capture sheet in INTERVIEW-KIT.md):

    --- Beta tester N ---
    Date / name / how they use Claude Code (solo/team, plan):
    Rules that fired in their export (and how often):
    Cost / cache / profile shape:
    Q1 did the HUD change what they did (story):
    Q2 confusing / noisy / ignored:
    Q3 would keep installed (and why / why not):
    Pulled toward a full interview? (y/n)

## Decision signal

If multiple testers' exports show the rules firing AND they report the HUD
changed a real decision, the wedge generalizes and the pilot is worth widening.
If exports are quiet (rules rarely fire) or the HUD gets ignored, that is the
signal to fix before chasing more testers, not a reason to add features.
