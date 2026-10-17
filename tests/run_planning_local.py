"""Run the stage 4 gate locally against the real HTTP API, without Supabase secrets.

Usage: backend/.venv/Scripts/python tests/run_planning_local.py [--contracts-only] [--project P] [--grep G]
Requires frontend and tests/e2e node_modules and Playwright Chromium installed.
The test server (backend/tests/planning_server.py, clinic F = golden set 5) and Vite stop on completion or failure.
"""

import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import httpx

from run_reports_local import wait_ready

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "local-planning-only"
VIEWPORTS = ("desktop-1280", "tablet-820", "mobile-390")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts-only", action="store_true")
    parser.add_argument("--project", help="Run one Playwright viewport instead of all three")
    parser.add_argument("--grep", help="Run only matching Playwright scenarios")
    args = parser.parse_args()
    artifacts = ROOT / "test-results" / "planning-local"
    artifacts.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    api_url = f"http://127.0.0.1:{port}"
    env = dict(os.environ, VF_LOCAL_PLANNING_TESTS="1", PYTHONUTF8="1")
    processes = []
    logs = []

    def start(command, cwd, name):
        log = (artifacts / f"{name}.log").open("w", encoding="utf-8")
        logs.append(log)
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
        processes.append(process)
        return process

    api_command = [
        sys.executable, "-m", "uvicorn", "tests.planning_server:app", "--host", "127.0.0.1", "--port", str(port)
    ]

    def restart_api(api=None):
        # Writing e2e scenarios change clinic F in memory: contract tests get a fresh copy.
        if api is not None:
            api.terminate()
            api.wait(timeout=10)
            processes.remove(api)
        api = start(api_command, ROOT / "backend", "api")
        wait_ready(api_url + "/healthz", api)
        return api

    try:
        api = restart_api()
        env.update(VF_API_URL=api_url, VF_SEEDED_SET05="1", VF_CONTRACT_WRITES="1")
        for letter in ("A", "B", "F"):
            response = httpx.post(
                api_url + "/auth/v1/token",
                json={"email": f"test-{letter.lower()}@vetfinance.test", "password": PASSWORD},
            )
            response.raise_for_status()
            env[f"VF_TOKEN_{letter}"] = response.json()["access_token"]
        if not args.contracts_only:
            env.update(
                VITE_API_URL=api_url,
                VITE_SUPABASE_URL=api_url,
                VITE_SUPABASE_ANON_KEY="local-anon",
                VF_WEB_URL="http://127.0.0.1:5173",
                VF_E2E_EMAIL="test-f@vetfinance.test",
                VF_E2E_PASSWORD=PASSWORD,
                VF_E2E_SET05="1",
                VF_E2E_WRITE="1",
            )
            node = shutil.which("node")
            if not node:
                raise RuntimeError("Node.js is required")
            web = start(
                [node, "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
                ROOT / "frontend",
                "web",
            )
            wait_ready(env["VF_WEB_URL"], web)
            # One viewport per fresh API: writing scenarios leave closed obligations in the list by design.
            for project in [args.project] if args.project else VIEWPORTS:
                command = [
                    node, "node_modules/@playwright/test/cli.js", "test", "calendar.spec.ts", "--workers=1",
                    "--project", project,
                ]
                if args.grep:
                    command += ["--grep", args.grep]
                subprocess.run(command, cwd=ROOT / "tests/e2e", env=env, check=True)
                api = restart_api(api)
        subprocess.run(
            [sys.executable, "-m", "pytest", "tests/contract/test_stage4_contract.py", "-q", "-rs", "-p", "no:cacheprovider"],
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
