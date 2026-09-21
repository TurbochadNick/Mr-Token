"""One-command, synthetic Savings Decision Card demo with host-sentinel proof."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from mrtoken.savings_card import build_savings_card, render_savings_card


_SENTINELS = (".claude/settings.json", ".codex/hooks.json", ".codex/config.toml")
_ROUTING = {
    "baseline": "synthetic-baseline",
    "candidate": "synthetic-candidate",
    "capability_floor": "fixture-floor",
    "budget": "fixture-budget",
    "oracle": "synthetic completion oracle",
}
_EXPECTED_ACTION = "routing experiment candidate"


def _fingerprint(path: Path) -> dict:
    if not path.exists():
        return {"exists": False, "sha256": None}
    try:
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        return {"exists": True, "sha256": digest}
    except OSError as exc:
        return {"exists": True, "sha256": None, "error": type(exc).__name__}


def _sentinels(home: Path) -> dict:
    return {str(home / relative): _fingerprint(home / relative) for relative in _SENTINELS}


def run(root: str | None = None, *, expected_action: str = _EXPECTED_ACTION) -> tuple[int, str]:
    """Run the demo and return its process-compatible status and deterministic report."""
    actual_home = Path.home()
    before = _sentinels(actual_home)
    root_path = Path(root) if root else Path(tempfile.mkdtemp(prefix="mrtoken-savings-demo-"))
    home, data, project = root_path / "home", root_path / "data", root_path / "project"
    saved = {key: os.environ.get(key) for key in
             ("HOME", "XDG_DATA_HOME", "MRTOKEN_DATA_DIR", "MRTOKEN_PRICES", "MRTOKEN_DB", "TOKEN_TITHE_DB")}
    try:
        for directory in (home, data, project):
            directory.mkdir(parents=True, exist_ok=True)
        os.environ.update({"HOME": str(home), "XDG_DATA_HOME": str(data),
                           "MRTOKEN_DATA_DIR": str(data), "MRTOKEN_PRICES": ""})
        os.environ.pop("MRTOKEN_DB", None)
        os.environ.pop("TOKEN_TITHE_DB", None)
        card = build_savings_card([], routing=_ROUTING)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    after = _sentinels(actual_home)
    card_ok = card.get("action") == expected_action and card.get("advisory") is True
    sentinel_ok = before == after and all(
        item.get("sha256") is not None or not item.get("exists") for item in before.values())
    root_ok = all(directory.is_dir() and directory.is_relative_to(root_path) for directory in (home, data, project))
    ok = card_ok and sentinel_ok and root_ok
    lines = ["MR Token disposable Savings Decision Card demo", f"disposable root: {root_path}",
             "synthetic trigger: routing baseline=synthetic-baseline candidate=synthetic-candidate "
             "capability_floor=fixture-floor budget=fixture-budget oracle=synthetic completion oracle",
             f"disposable state: home={home} data={data} project={project}",
             "measured session data: UNKNOWN — this synthetic demo has no session or provider call",
             "provider/model call or switch: none"]
    lines.extend(render_savings_card(card))
    for path, fingerprint in before.items():
        digest = fingerprint.get("sha256") or ("absent" if not fingerprint["exists"] else "UNAVAILABLE")
        lines.append(f"sentinel: {path} sha256={digest} unchanged={'yes' if fingerprint == after[path] else 'no'}")
    lines.append(f"confinement: {'PASS' if sentinel_ok and root_ok else 'FAIL'}")
    lines.append(f"oracle: {'PASS' if card_ok else 'FAIL'} expected={expected_action!r} actual={card.get('action')!r}")
    return (0 if ok else 1), "\n".join(lines)


def main() -> int:
    status, text = run()
    print(text)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
