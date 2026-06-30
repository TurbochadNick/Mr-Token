# MR Token governance

MR Token is still in `~/Projects/gate-pending/` because ownership is not fully
resolved. See [OWNERSHIP_GATE.md](../OWNERSHIP_GATE.md) for the source-of-truth
gate.

Current facts:

- Zach owns the Python backend work in this checkout.
- Nick / TurbochadNick co-built the TypeScript and web surfaces.
- The repository remote is under Nick's GitHub account:
  `git@github.com:TurbochadNick/Mr-Token.git`.
- The project is part of an active BYU TTO pilot, so BYU may assert a claim.

Before broad beta expansion or commercial packaging:

1. Get BYU TTO's written position on ownership.
2. Get Zach and Nick's written ownership split.
3. Decide the permanent storage bucket: personal, shared, or business.
4. Move the repo out of `gate-pending/` only after the ownership gate closes.

Tester-facing language should stay modest until this is resolved: local beta,
research/pilot, no hosted service, no production SLA.
