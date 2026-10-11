"""Prints shell lines that export VF_API_URL / VF_TOKEN_A / VF_TOKEN_B (and VF_TOKEN_C when VF_TEST_EMAIL_C is set).

Reads backend/.env (VF_TEST_EMAIL_*, VF_TEST_PASSWORD, SUPABASE_URL) and the anon key from frontend/.env at run time.
Nothing is written to disk; the password never appears in tests/. Usage (bash):
    eval "$(python tests/contract/get_tokens.py)"
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = os.environ.get("VF_API_URL", "https://vetfinance-api-production.up.railway.app")


def load_env(path):
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def sign_in(base, anon, email, password):
    req = urllib.request.Request(f"{base}/auth/v1/token?grant_type=password",
                                 data=json.dumps({"email": email, "password": password}).encode(),
                                 headers={"apikey": anon, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)["access_token"]


def main():
    be, fe = load_env(ROOT / "backend" / ".env"), load_env(ROOT / "frontend" / ".env")
    base, anon, pwd = be["SUPABASE_URL"].rstrip("/"), fe["VITE_SUPABASE_ANON_KEY"], be["VF_TEST_PASSWORD"]
    print(f"export VF_API_URL='{API}'")
    for letter in "ABC":
        email = be.get(f"VF_TEST_EMAIL_{letter}")
        if email:
            print(f"export VF_TOKEN_{letter}='{sign_in(base, anon, email, pwd)}'")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # no secrets in the message
        print(f"echo 'get_tokens failed: {type(exc).__name__}' >&2", file=sys.stdout)
        sys.exit(1)
