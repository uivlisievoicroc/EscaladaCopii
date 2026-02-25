#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path


def http_get_text(url: str, timeout: float = 2.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, body


def http_get_json(url: str, timeout: float = 2.0) -> dict:
    status, body = http_get_text(url, timeout=timeout)
    if status != 200:
        raise RuntimeError(f"Unexpected status {status} for {url}")
    return json.loads(body)


def wait_for_runtime(port_min: int, port_max: int, timeout_sec: float = 45.0) -> tuple[int, dict]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        for port in range(port_min, port_max + 1):
            try:
                payload = http_get_json(f"http://127.0.0.1:{port}/api/runtime", timeout=0.5)
                return port, payload
            except Exception:
                continue
        time.sleep(0.25)
    raise TimeoutError("Timed out waiting for /api/runtime.")


def assert_spa_and_assets(port: int) -> None:
    status, html = http_get_text(f"http://127.0.0.1:{port}/", timeout=2.0)
    if status != 200:
        raise AssertionError(f"GET / failed with status {status}")
    if "<div id=\"root\">" not in html and "<div id='root'>" not in html:
        raise AssertionError("Root HTML does not look like React entry page.")

    match = re.search(r'(?:src|href)="(/assets/[^"]+)"', html)
    if not match:
        raise AssertionError("Could not find /assets/... in index HTML.")

    asset_path = match.group(1)
    asset_status, _ = http_get_text(f"http://127.0.0.1:{port}{asset_path}", timeout=2.0)
    if asset_status != 200:
        raise AssertionError(f"Asset check failed for {asset_path}: status={asset_status}")


def assert_docs_openapi(port: int) -> None:
    docs_status, _ = http_get_text(f"http://127.0.0.1:{port}/docs", timeout=2.0)
    redoc_status, _ = http_get_text(f"http://127.0.0.1:{port}/redoc", timeout=2.0)
    openapi_status, _ = http_get_text(f"http://127.0.0.1:{port}/openapi.json", timeout=2.0)
    if docs_status != 200:
        raise AssertionError(f"/docs expected 200, got {docs_status}")
    if redoc_status != 200:
        raise AssertionError(f"/redoc expected 200, got {redoc_status}")
    if openapi_status != 200:
        raise AssertionError(f"/openapi.json expected 200, got {openapi_status}")


@contextmanager
def reserve_port(port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(1)
    try:
        yield
    finally:
        sock.close()


@contextmanager
def noop_context():
    yield


def start_process(args: argparse.Namespace) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["ESCALADA_SMOKE_NON_HARDWARE"] = "1"

    if args.target == "source":
        cmd = [
            "poetry",
            "run",
            "python",
            "-m",
            "escalada.launcher",
            "--host",
            "127.0.0.1",
            "--port-min",
            str(args.port_min),
            "--port-max",
            str(args.port_max),
        ]
        return subprocess.Popen(cmd, cwd=args.api_dir, env=env)

    if not args.binary:
        raise ValueError("--binary is required when --target packaged")

    cmd = [
        str(args.binary),
        "--host",
        "127.0.0.1",
        "--port-min",
        str(args.port_min),
        "--port-max",
        str(args.port_max),
    ]
    return subprocess.Popen(cmd, cwd=args.binary.parent, env=env)


def stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def run_case(args: argparse.Namespace, reserve_8000: bool) -> None:
    ctx = reserve_port(8000) if reserve_8000 else noop_context()
    with ctx:
        proc = start_process(args)
        try:
            discovered_port, runtime_payload = wait_for_runtime(args.port_min, args.port_max)
            reported_port = int(runtime_payload.get("port", -1))

            if reported_port != discovered_port:
                raise AssertionError(
                    f"/api/runtime port mismatch: discovered={discovered_port}, reported={reported_port}"
                )

            if reserve_8000:
                if reported_port == 8000:
                    raise AssertionError("Expected fallback port when 8000 is reserved.")
                if not (args.port_min <= reported_port <= args.port_max):
                    raise AssertionError(f"Fallback port out of range: {reported_port}")
            else:
                if reported_port != 8000:
                    raise AssertionError(f"Expected 8000 when free, got {reported_port}")

            assert_spa_and_assets(reported_port)
            assert_docs_openapi(reported_port)
        finally:
            stop_process(proc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Escalada smoke runtime checks.")
    parser.add_argument("--target", choices=["source", "packaged"], default="source")
    parser.add_argument("--api-dir", type=Path, default=Path("repos/escalada-api"))
    parser.add_argument("--binary", type=Path, default=None)
    parser.add_argument("--port-min", type=int, default=8000)
    parser.add_argument("--port-max", type=int, default=8100)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.api_dir = args.api_dir.resolve()
    if args.binary:
        args.binary = args.binary.resolve()

    if args.target == "source" and not args.api_dir.exists():
        raise FileNotFoundError(f"API dir not found: {args.api_dir}")

    run_case(args, reserve_8000=False)
    run_case(args, reserve_8000=True)
    print("Smoke checks passed.")


if __name__ == "__main__":
    main()
