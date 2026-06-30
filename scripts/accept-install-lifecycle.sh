#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PY=""
for c in "${PYTHON:-}" python3.13 python3.12 python3.11 python3; do
  [[ -n "$c" ]] || continue
  command -v "$c" >/dev/null 2>&1 || continue
  if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$c"
    break
  fi
done

if [[ -z "$PY" ]]; then
  echo "need Python 3.11+ (set PYTHON=/path/to/python if needed)" >&2
  exit 1
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/mrtoken-install-accept.XXXXXX")"
cleanup() {
  chmod -R u+w "$TMP" 2>/dev/null || true
  rm -rf "$TMP"
}
trap cleanup EXIT

HOME_DIR="$TMP/home"
PROJECT="$TMP/project"
CLONE="$TMP/clone"
VENV="$TMP/venv"
mkdir -p "$HOME_DIR/.codex" "$PROJECT/.git"

"$PY" -m venv "$VENV"
VPY="$VENV/bin/python"
PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 "$VPY" -m pip install -e "$ROOT/backend" -q

PATH="$VENV/bin:$PATH" HOME="$HOME_DIR" "$VPY" - "$PROJECT" <<'PY'
import json
import os
import sys

project = sys.argv[1]

from mrtoken.doctor import check_install, repair_install, write_bundle
from mrtoken.install import init, uninstall

def require(condition, message):
    if not condition:
        raise SystemExit(message)

init(project_root=project, emit=lambda *a, **k: None)
report = check_install(project_root=project)
require(report["ok"], json.dumps(report, indent=2))

bundle = os.path.join(project, "doctor-bundle.json")
write_bundle(report, bundle)
with open(bundle, encoding="utf-8") as handle:
    doc = json.load(handle)
require(doc["schema"] == "mrtoken.doctor.bundle.v1", "bad doctor bundle schema")

uninstall(project_root=project, emit=lambda *a, **k: None)
after_uninstall = check_install(project_root=project)
require(not after_uninstall["ok"], "doctor should fail after uninstall removes hooks/skills")

repair_install(project_root=project, emit=lambda *a, **k: None)
after_repair = check_install(project_root=project)
require(after_repair["ok"], json.dumps(after_repair, indent=2))

print("init/doctor/bundle/uninstall/repair ok")
PY

git clone "$ROOT" "$CLONE" >/dev/null 2>&1
PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 "$VPY" -m pip install -e "$CLONE/backend" -q

UPDATE_OUT="$(
  cd "$CLONE"
  PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
    PATH="$VENV/bin:$PATH" HOME="$HOME_DIR" "$VPY" -m mrtoken.cli update
)"
case "$UPDATE_OUT" in
  *"updated"*) ;;
  *)
    echo "$UPDATE_OUT" >&2
    echo "update smoke did not report success" >&2
    exit 1
    ;;
esac

PATH="$VENV/bin:$PATH" HOME="$HOME_DIR" "$VPY" -m mrtoken.cli doctor --project-root "$CLONE" >/dev/null
echo "update smoke ok"
echo "install lifecycle acceptance passed"
