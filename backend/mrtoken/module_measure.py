#!/usr/bin/env python3
"""Lab-only measurement harness for external token-saver modules.

This is ROADMAP 7.3's safety boundary: measure a module in a reversible sandbox
before any real agent routing, wrapping, or default enablement. The harness can:

  - compare before/after text artifacts and optionally record realized savings;
  - parse Headroom proxy JSONL logs for tokens_before/tokens_after deltas;
  - start a Headroom proxy in an isolated local sandbox for a health/file-write
    probe, without forwarding a real agent or provider request.

It intentionally does not install, register, wrap, or enable any external module.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import nullcontext
from typing import Any

QUALITY = ("unknown", "pass", "fail", "neutral")
HEADROOM_LOG_BEFORE_KEYS = (
    "tokens_before",
    "input_tokens_before",
    "original_tokens",
    "raw_tokens",
)
HEADROOM_LOG_AFTER_KEYS = (
    "tokens_after",
    "input_tokens_after",
    "compressed_tokens",
    "optimized_tokens",
)


def estimate_tokens(text: str) -> int:
    """Cheap, deterministic estimate for local artifact comparisons."""
    return max(0, len(text.encode("utf-8", "replace")) // 4)


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _first_number(row: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        val = row.get(key)
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)):
            return int(val)
    return None


def _quality_to_outcome(tokens_delta: int, quality: str) -> int:
    if quality == "fail":
        return -1
    if quality == "pass" and tokens_delta > 0:
        return 1
    if tokens_delta < 0:
        return -1
    return 0


def record_measurement(module: str, tokens_delta: int, quality: str,
                       session_id: str = "", note: str = "") -> dict:
    """Record savings/outcome under the module name. Unknown quality records only
    positive realized savings; outcomes need an explicit quality verdict."""
    from mrtoken import outcomes, savings

    quality = quality if quality in QUALITY else "unknown"
    tokens_saved = max(0, int(tokens_delta or 0))
    savings.record(module, tokens_saved, session_id=session_id)
    outcome_recorded = False
    if quality != "unknown":
        outcomes.record(module, _quality_to_outcome(tokens_delta, quality),
                        session_id=session_id, note=note)
        outcome_recorded = True
    return {
        "savings_recorded": tokens_saved > 0,
        "outcome_recorded": outcome_recorded,
    }


def _measurement_report(module: str, before_tokens: int, after_tokens: int,
                        source: str, quality: str = "unknown",
                        record: bool = False, session_id: str = "",
                        note: str = "", extra: dict | None = None) -> dict:
    delta = int(before_tokens or 0) - int(after_tokens or 0)
    report = {
        "kind": source,
        "module": module,
        "before_tokens": int(before_tokens or 0),
        "after_tokens": int(after_tokens or 0),
        "tokens_delta": delta,
        "tokens_saved": max(0, delta),
        "compression_ratio": (
            round(after_tokens / before_tokens, 4) if before_tokens else None
        ),
        "quality": quality,
        "recorded": False,
    }
    if extra:
        report.update(extra)
    if record:
        report.update(record_measurement(module, delta, quality, session_id, note))
        report["recorded"] = True
    return report


def measure_files(module: str, before_path: str, after_path: str,
                  quality: str = "unknown", record: bool = False,
                  session_id: str = "") -> dict:
    before = estimate_tokens(_read(before_path))
    after = estimate_tokens(_read(after_path))
    return _measurement_report(
        module, before, after, "file_pair", quality=quality, record=record,
        session_id=session_id,
        note=f"module-measure file pair: {os.path.basename(before_path)} -> "
             f"{os.path.basename(after_path)}",
        extra={"before_path": before_path, "after_path": after_path},
    )


def parse_headroom_log(path: str) -> dict:
    """Parse Headroom proxy JSONL token deltas without storing message content."""
    rows_seen = rows_measured = bad_lines = 0
    before_total = after_total = 0
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows_seen += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            before = _first_number(row, HEADROOM_LOG_BEFORE_KEYS)
            after = _first_number(row, HEADROOM_LOG_AFTER_KEYS)
            if before is None or after is None:
                continue
            before_total += before
            after_total += after
            rows_measured += 1
    return {
        "rows_seen": rows_seen,
        "rows_measured": rows_measured,
        "bad_lines": bad_lines,
        "before_tokens": before_total,
        "after_tokens": after_total,
        "tokens_delta": before_total - after_total,
        "tokens_saved": max(0, before_total - after_total),
    }


def measure_headroom_log(module: str, log_path: str, quality: str = "unknown",
                         record: bool = False, session_id: str = "") -> dict:
    parsed = parse_headroom_log(log_path)
    return _measurement_report(
        module, parsed["before_tokens"], parsed["after_tokens"], "headroom_log",
        quality=quality, record=record, session_id=session_id,
        note=f"module-measure Headroom proxy log: {os.path.basename(log_path)}",
        extra={
            "log_path": log_path,
            "rows_seen": parsed["rows_seen"],
            "rows_measured": parsed["rows_measured"],
            "bad_lines": parsed["bad_lines"],
        },
    )


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _safe_proxy_env(sandbox: str) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.path.join(sandbox, "home"),
        "XDG_DATA_HOME": os.path.join(sandbox, "xdg"),
        "TMPDIR": os.path.join(sandbox, "tmp"),
        "HEADROOM_UPDATE_CHECK": "off",
        "HEADROOM_TELEMETRY": "off",
        "HEADROOM_NO_SUBSCRIPTION_TRACKING": "1",
        "HEADROOM_STATELESS": "true",
    }
    for key in ("LANG", "LC_ALL"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    for path_key in ("HOME", "XDG_DATA_HOME", "TMPDIR"):
        os.makedirs(env[path_key], exist_ok=True)
    return env


def _list_files(root: str) -> list[dict]:
    files: list[dict] = []
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = None
            files.append({"path": os.path.relpath(full, root), "bytes": size})
    return sorted(files, key=lambda row: row["path"])


def _clip(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... clipped {len(text) - limit} chars ..."


def _wait_local_endpoint(port: int, timeout_s: float,
                         proc: subprocess.Popen | None = None) -> dict:
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return {"ok": False, "url": f"http://127.0.0.1:{port}/livez",
                    "error": f"process exited with code {proc.returncode}"}
        for path in ("/livez", "/healthz", "/"):
            url = f"http://127.0.0.1:{port}{path}"
            try:
                with urllib.request.urlopen(url, timeout=0.5) as resp:
                    return {"ok": True, "url": url, "status": resp.status}
            except urllib.error.HTTPError as exc:
                return {"ok": True, "url": url, "status": exc.code}
            except OSError as exc:
                last_error = str(exc)
        time.sleep(0.1)
    return {"ok": False, "url": f"http://127.0.0.1:{port}/livez",
            "error": last_error or "timeout"}


def probe_headroom_proxy(headroom_bin: str = "headroom", timeout_s: float = 8.0,
                         keep_sandbox: bool = False,
                         sandbox_root: str | None = None) -> dict:
    """Start Headroom's proxy locally, hit only a health endpoint, then stop it.

    The command uses --stateless/--no-optimize/no telemetry. It does not set
    ANTHROPIC_BASE_URL or OPENAI_BASE_URL, and it never forwards a model request.
    """
    if sandbox_root:
        os.makedirs(sandbox_root, exist_ok=True)
        ctx = nullcontext(sandbox_root)
        cleanup = False
    elif keep_sandbox:
        root = tempfile.mkdtemp(prefix="mrtoken-module-headroom-")
        ctx = nullcontext(root)
        cleanup = False
    else:
        ctx = tempfile.TemporaryDirectory(prefix="mrtoken-module-headroom-")
        cleanup = True

    with ctx as sandbox:
        env = _safe_proxy_env(sandbox)
        resolved = headroom_bin if os.path.isabs(headroom_bin) else shutil.which(
            headroom_bin, path=env.get("PATH", "")
        )
        if not resolved:
            return {
                "kind": "headroom_proxy_probe",
                "ok": False,
                "error": f"headroom binary not found: {headroom_bin}",
                "sandbox": sandbox,
                "sandbox_removed": cleanup,
            }
        port = _free_port()
        log_file = os.path.join(sandbox, "headroom-proxy.jsonl")
        cmd = [
            resolved, "proxy",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--no-optimize",
            "--stateless",
            "--no-telemetry",
            "--no-subscription-tracking",
            "--no-ccr-inject-tool",
            "--request-timeout-seconds", "5",
            "--connect-timeout-seconds", "1",
            "--log-file", log_file,
        ]
        proc = subprocess.Popen(
            cmd, env=env, cwd=sandbox, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )
        endpoint = {"ok": False, "error": "process exited before health probe"}
        try:
            if proc.poll() is None:
                endpoint = _wait_local_endpoint(port, timeout_s, proc=proc)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    stdout, stderr = proc.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate(timeout=3)
            else:
                stdout, stderr = proc.communicate(timeout=3)
        return {
            "kind": "headroom_proxy_probe",
            "ok": bool(endpoint.get("ok")),
            "command": cmd,
            "controlled_env": {k: env[k] for k in sorted(env) if k.startswith("HEADROOM_")},
            "local_endpoint": endpoint,
            "exit_code": proc.returncode,
            "sandbox": sandbox,
            "sandbox_removed": cleanup,
            "files": _list_files(sandbox),
            "stdout": _clip(stdout or ""),
            "stderr": _clip(stderr or ""),
        }


def format_report(report: dict) -> str:
    kind = report.get("kind")
    if kind == "headroom_proxy_probe":
        lines = [
            "module-measure: Headroom proxy probe",
            f"  ok: {report.get('ok')}",
            f"  endpoint: {report.get('local_endpoint')}",
            f"  sandbox: {report.get('sandbox')} "
            f"({'removed' if report.get('sandbox_removed') else 'kept'})",
            "  files written:",
        ]
        files = report.get("files") or []
        if not files:
            lines.append("    (none)")
        else:
            for row in files:
                lines.append(f"    {row['path']} ({row.get('bytes')} bytes)")
        if report.get("stderr"):
            lines.append("  stderr:")
            lines.append(report["stderr"])
        return "\n".join(lines)

    lines = [
        f"module-measure: {report.get('module')} ({kind})",
        f"  before: ~{report.get('before_tokens', 0):,} tok",
        f"  after:  ~{report.get('after_tokens', 0):,} tok",
        f"  delta:  ~{report.get('tokens_delta', 0):,} tok "
        f"(saved ~{report.get('tokens_saved', 0):,})",
        f"  quality: {report.get('quality', 'unknown')}",
        f"  recorded: {report.get('recorded', False)}",
    ]
    if "rows_measured" in report:
        lines.append(
            f"  log rows: {report.get('rows_measured')}/"
            f"{report.get('rows_seen')} measured"
        )
    return "\n".join(lines)
