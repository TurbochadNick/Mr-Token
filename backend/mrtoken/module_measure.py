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
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

QUALITY = ("unknown", "pass", "fail", "neutral")
HEADROOM_LOG_BEFORE_KEYS = (
    "tokens_before",
    "input_tokens_original",
    "input_tokens_before",
    "original_tokens",
    "attempted_input_tokens",
    "raw_tokens",
)
HEADROOM_LOG_AFTER_KEYS = (
    "tokens_after",
    "input_tokens_optimized",
    "input_tokens_after",
    "optimized_tokens",
    "compressed_tokens",
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
            saved = _first_number(row, ("tokens_saved", "saved", "tokens_delta"))
            if before is None and after is not None and saved is not None:
                before = after + max(saved, 0)
            if after is None and before is not None and saved is not None:
                after = max(before - max(saved, 0), 0)
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


def _safe_proxy_env(sandbox: str, stateless: bool = True) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.path.join(sandbox, "home"),
        "XDG_DATA_HOME": os.path.join(sandbox, "xdg"),
        "TMPDIR": os.path.join(sandbox, "tmp"),
        "HEADROOM_UPDATE_CHECK": "off",
        "HEADROOM_TELEMETRY": "off",
        "HEADROOM_NO_SUBSCRIPTION_TRACKING": "1",
    }
    if stateless:
        env["HEADROOM_STATELESS"] = "true"
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


class _FakeAnthropicHandler(BaseHTTPRequestHandler):
    server_version = "MrTokenFakeAnthropic/1.0"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length)
        self.server.requests.append({
            "method": "POST",
            "path": self.path,
            "headers": {k: v for k, v in self.headers.items()},
            "body": body.decode("utf-8", "replace"),
        })
        response = {
            "id": "msg_mrtoken_synthetic",
            "type": "message",
            "role": "assistant",
            "model": "claude-3-5-sonnet-20241022",
            "content": [{"type": "text", "text": "synthetic upstream ok"}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 123, "output_tokens": 5},
        }
        data = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # silence test/probe noise
        return


def _start_fake_anthropic_upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeAnthropicHandler)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, int(server.server_address[1])


def _synthetic_tool_result(chars: int = 48_000) -> str:
    line = "2026-07-08T00:00:00Z INFO worker=alpha trace=synthetic value=1234567890\n"
    repeats = max(1, chars // len(line))
    return (line * repeats)[:chars]


def _synthetic_anthropic_payload(chars: int = 48_000) -> dict:
    return _anthropic_payload(_synthetic_tool_result(chars))


def _anthropic_payload(tool_result: str) -> dict:
    """Build the one safe request shape used by the local proxy probe."""
    return {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 64,
        "tools": [{
            "name": "Bash",
            "description": "Run a shell command and return output.",
            "input_schema": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        }],
        "messages": [
            {"role": "user", "content": "Run the diagnostic and inspect the log."},
            {"role": "assistant", "content": [{
                "type": "tool_use",
                "id": "toolu_mrtoken_synthetic",
                "name": "Bash",
                "input": {"command": "cat synthetic-large.log"},
            }]},
            {"role": "user", "content": [{
                "type": "tool_result",
                "tool_use_id": "toolu_mrtoken_synthetic",
                "content": tool_result,
            }]},
            {"role": "user", "content": "Summarize whether the log contains ERROR."},
        ],
    }


def _post_json(url: str, payload: dict, timeout_s: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": "mrtoken-synthetic-key",
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", "replace")
            return {"ok": 200 <= resp.status < 300, "status": resp.status,
                    "body": body[:2000]}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return {"ok": False, "status": exc.code, "body": body[:2000]}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def _get_json(url: str, timeout_s: float) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            return {"ok": 200 <= resp.status < 300, "status": resp.status,
                    "body": json.loads(resp.read().decode("utf-8", "replace"))}
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}


def _quality_check(compressed_request: str, original: str, proxy_port: int,
                   timeout_s: float) -> dict:
    """Verify Headroom's loopback CCR retrieval without retaining payload text."""
    match = re.search(r"<<ccr:([a-f0-9]{12,24})\\b", compressed_request)
    if not match:
        return {"round_trip": False, "needles": 0, "needles_ok": False,
                "reason": "no CCR marker"}
    retrieved = _get_json(f"http://127.0.0.1:{proxy_port}/v1/retrieve/{match.group(1)}", timeout_s)
    recovered = retrieved.get("body", {}).get("original_content") if retrieved.get("ok") else None
    lines = [line for line in original.splitlines() if line][:3]
    return {
        "round_trip": recovered == original,
        "needles": len(lines),
        "needles_ok": isinstance(recovered, str) and all(line in recovered for line in lines),
        "retrieval_ok": bool(retrieved.get("ok")),
    }


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


def probe_headroom_synthetic_traffic(headroom_bin: str = "headroom",
                                     timeout_s: float = 12.0,
                                     keep_sandbox: bool = False,
                                     synthetic_chars: int = 48_000,
                                     payload_paths: list[str] | None = None,
                                     enable_kompress: bool = False,
                                     asset_cache: str | None = None,
                                     record: bool = False,
                                     quality: str = "unknown",
                                     session_id: str = "") -> dict:
    """Route one synthetic Anthropic request through Headroom to a fake upstream.

    This proves the measurement loop without a real provider or agent: localhost
    client -> Headroom proxy -> localhost fake Anthropic endpoint. Request logging
    requires Headroom to run non-stateless, so all writes are confined to the temp
    sandbox and reported.
    """
    if keep_sandbox:
        root = tempfile.mkdtemp(prefix="mrtoken-module-headroom-traffic-")
        ctx = nullcontext(root)
        cleanup = False
    else:
        ctx = tempfile.TemporaryDirectory(prefix="mrtoken-module-headroom-traffic-")
        cleanup = True

    with ctx as sandbox:
        env = _safe_proxy_env(sandbox, stateless=False)
        if asset_cache:
            source = os.path.join(asset_cache, "hf")
            if not os.path.isdir(source):
                return {
                    "kind": "headroom_synthetic_traffic",
                    "ok": False,
                    "error": f"Headroom asset cache not found: {source}",
                    "sandbox": sandbox,
                    "sandbox_removed": cleanup,
                }
            shutil.copytree(source, os.path.join(sandbox, "hf"))
        env.update({
            "HEADROOM_OFFLINE": "1",
            "HEADROOM_BINARIES_OFFLINE": "1",
            "HEADROOM_CCR_BACKEND": "disk" if enable_kompress else "memory",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HOME": os.path.join(sandbox, "hf"),
            "HUGGINGFACE_HUB_CACHE": os.path.join(sandbox, "hf", "hub"),
            "XDG_CACHE_HOME": os.path.join(sandbox, "cache"),
            "HEADROOM_BINARIES_CACHE": os.path.join(sandbox, "binaries"),
            "TIKTOKEN_CACHE_DIR": os.path.join(sandbox, "tiktoken-cache"),
        })
        if not enable_kompress:
            env.update({
                "HEADROOM_DISABLE_KOMPRESS": "1",
                "HEADROOM_NO_CCR_INJECT_TOOL": "1",
                "HEADROOM_TIKTOKEN_LOAD_TIMEOUT_SECONDS": "0",
            })
        resolved = headroom_bin if os.path.isabs(headroom_bin) else shutil.which(
            headroom_bin, path=env.get("PATH", "")
        )
        if not resolved:
            return {
                "kind": "headroom_synthetic_traffic",
                "ok": False,
                "error": f"headroom binary not found: {headroom_bin}",
                "sandbox": sandbox,
                "sandbox_removed": cleanup,
            }

        upstream, upstream_thread, upstream_port = _start_fake_anthropic_upstream()
        proc = None
        stdout = stderr = ""
        try:
            proxy_port = _free_port()
            log_file = os.path.join(sandbox, "headroom-proxy.jsonl")
            cmd = [
                resolved, "proxy",
                "--host", "127.0.0.1",
                "--port", str(proxy_port),
                "--no-telemetry",
                "--no-subscription-tracking",
                "--intercept-tool-results",
                "--no-cache",
                "--no-rate-limit",
                "--no-http2",
                "--request-timeout-seconds", "5",
                "--connect-timeout-seconds", "1",
                "--anthropic-api-url", f"http://127.0.0.1:{upstream_port}",
                "--log-file", log_file,
            ]
            if not enable_kompress:
                cmd.extend(["--no-ccr-inject-tool", "--lossless", "--disable-kompress"])
            proc = subprocess.Popen(
                cmd, env=env, cwd=sandbox, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            endpoint = _wait_local_endpoint(proxy_port, timeout_s, proc=proc)
            payload_texts = [("synthetic", _synthetic_tool_result(synthetic_chars))]
            if payload_paths:
                payload_texts = [(path, _read(path)) for path in payload_paths]
            requests = []
            for label, tool_result in payload_texts:
                payload = _anthropic_payload(tool_result)
                request = {"ok": False, "error": "proxy not ready"}
                if endpoint.get("ok"):
                    request = _post_json(
                        f"http://127.0.0.1:{proxy_port}/v1/messages",
                        payload,
                        timeout_s,
                    )
                quality_check = {"round_trip": None, "needles": 0, "needles_ok": None}
                if enable_kompress and request.get("ok") and upstream.requests:
                    quality_check = _quality_check(
                        upstream.requests[-1]["body"], tool_result, proxy_port, timeout_s
                    )
                requests.append({"path": label, "request": request,
                                 "input_bytes": len(tool_result.encode("utf-8", "replace")),
                                 "quality": quality_check})
            time.sleep(0.25)  # give the proxy log writer a moment to flush
        finally:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    stdout, stderr = proc.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate(timeout=3)
            elif proc:
                stdout, stderr = proc.communicate(timeout=3)
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(timeout=2)

        parsed = parse_headroom_log(log_file) if os.path.exists(log_file) else {
            "rows_seen": 0, "rows_measured": 0, "bad_lines": 0,
            "before_tokens": 0, "after_tokens": 0,
            "tokens_delta": 0, "tokens_saved": 0,
        }
        before = parsed["before_tokens"]
        after = parsed["after_tokens"]
        report = _measurement_report(
            "headroom", before, after, "headroom_synthetic_traffic",
            quality=quality, record=record, session_id=session_id,
            note="module-measure Headroom synthetic localhost traffic",
            extra={
                "ok": bool(endpoint.get("ok") and all(r["request"].get("ok") for r in requests)),
                "controlled_env": {k: env[k] for k in sorted(env)
                                   if k.startswith("HEADROOM_")},
                "local_endpoint": endpoint,
                "requests": requests,
                "fake_upstream_requests": len(getattr(upstream, "requests", [])),
                "kompress_requested": enable_kompress,
                "asset_cache_used": bool(asset_cache),
                "log_path": log_file,
                "rows_seen": parsed["rows_seen"],
                "rows_measured": parsed["rows_measured"],
                "bad_lines": parsed["bad_lines"],
                "command": cmd if "cmd" in locals() else [],
                "sandbox": sandbox,
                "sandbox_removed": cleanup,
                "files": _list_files(sandbox),
                "stdout": _clip(stdout or ""),
                "stderr": _clip(stderr or ""),
            },
        )
        return report


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

    if kind == "headroom_synthetic_traffic":
        lines = [
            "module-measure: Headroom synthetic traffic probe",
            f"  ok: {report.get('ok')}",
            f"  endpoint: {report.get('local_endpoint')}",
            f"  requests: {len(report.get('requests') or [])}",
            f"  fake upstream requests: {report.get('fake_upstream_requests')}",
            f"  log rows: {report.get('rows_measured')}/{report.get('rows_seen')} measured",
            f"  log delta: ~{report.get('tokens_delta', 0):,} tok "
            f"(saved ~{report.get('tokens_saved', 0):,})",
            f"  Kompress requested: {report.get('kompress_requested', False)}",
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
