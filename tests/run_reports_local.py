"""Run the stage 3 gate locally against the real HTTP API, without Supabase secrets.

Usage: backend/.venv/Scripts/python tests/run_reports_local.py [--contracts-only]
Requires frontend and tests/e2e node_modules and Playwright Chromium installed.
The test server and Vite stop on completion or failure. No production data is used.
"""

import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def wait_ready(url, process):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited with {process.returncode}: {url}")
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Server did not start: {url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts-only", action="store_true")
    parser.add_argument(
        "--project", help="Run one Playwright viewport instead of all three"
    )
    parser.add_argument("--grep", help="Run only matching Playwright scenarios")
    parser.add_argument(
        "--downloads", type=Path, help="Verify exports from a previous local run"
    )
    args = parser.parse_args()
    artifacts = ROOT / "test-results" / "reports-local"
    artifacts.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    api_url = f"http://127.0.0.1:{port}"
    env = dict(os.environ, VF_LOCAL_REPORT_TESTS="1", PYTHONUTF8="1")
    processes = []
    logs = []

    def start(command, cwd, name):
        log = (artifacts / f"{name}.log").open("w", encoding="utf-8")
        logs.append(log)
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT
        )
        processes.append(process)
        return process

    try:
        api = start(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "tests.report_server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            ROOT / "backend",
            "api",
        )
        wait_ready(api_url + "/healthz", api)
        env.update(VF_API_URL=api_url, VF_SEEDED_SET04="1")
        for letter in ("A", "B", "E"):
            response = httpx.post(
                api_url + "/auth/v1/token",
                json={
                    "email": f"test-{letter.lower()}@vetfinance.test",
                    "password": "local-reports-only",
                },
            )
            response.raise_for_status()
            env[f"VF_TOKEN_{letter}"] = response.json()["access_token"]
        # Never consume files from a previous run when the browser phase is omitted.
        env.pop("VF_E2E_DOWNLOADS", None)
        if args.downloads:
            if not args.downloads.is_dir():
                raise RuntimeError(f"Download folder does not exist: {args.downloads}")
            env.update(
                VF_E2E_DOWNLOADS=str(args.downloads.resolve()),
                VF_E2E_DOWNLOADS_CLINIC="E",
            )
        if not args.contracts_only:
            env.update(
                VITE_API_URL=api_url,
                VITE_SUPABASE_URL=api_url,
                VITE_SUPABASE_ANON_KEY="local-anon",
                VF_WEB_URL="http://127.0.0.1:5173",
                VF_E2E_EMAIL="test-e@vetfinance.test",
                VF_E2E_PASSWORD="local-reports-only",
                VF_E2E_SET04="1",
                VF_E2E_DOWNLOADS=(
                    str(args.downloads.resolve())
                    if args.downloads
                    else tempfile.mkdtemp(prefix="downloads-", dir=artifacts)
                ),
                VF_E2E_DOWNLOADS_CLINIC="E",
            )
            node = shutil.which("node")
            if not node:
                raise RuntimeError("Node.js is required")
            web = start(
                [
                    node,
                    "node_modules/vite/bin/vite.js",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5173",
                    "--strictPort",
                ],
                ROOT / "frontend",
                "web",
            )
            wait_ready(env["VF_WEB_URL"], web)
            command = [
                node,
                "node_modules/@playwright/test/cli.js",
                "test",
                "reports.spec.ts",
                "--workers=1",
            ]
            if args.project:
                command += ["--project", args.project]
            if args.grep:
                command += ["--grep", args.grep]
            subprocess.run(command, cwd=ROOT / "tests/e2e", env=env, check=True)
            if args.grep and not any(Path(env["VF_E2E_DOWNLOADS"]).glob("*.xlsx")):
                # A focused run may not contain export scenarios at all.
                env.pop("VF_E2E_DOWNLOADS")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/contract/test_stage3_contract.py",
                "-q",
                "-rs",
                "-p",
                "no:cacheprovider",
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
