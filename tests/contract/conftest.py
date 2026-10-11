import os

import pytest

httpx = pytest.importorskip("httpx", reason="httpx is not installed (pip install -r tests/contract/requirements.txt)")


def _env(name):
    v = os.environ.get(name)
    if not v:
        pytest.skip(f"{name} is not set; contract tests need VF_API_URL, VF_TOKEN_A, VF_TOKEN_B")
    return v


@pytest.fixture(scope="session")
def base_url():
    return _env("VF_API_URL").rstrip("/")


@pytest.fixture(scope="session")
def client_a(base_url):
    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {_env('VF_TOKEN_A')}"}, timeout=15) as c:
        yield c


@pytest.fixture(scope="session")
def client_b(base_url):
    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {_env('VF_TOKEN_B')}"}, timeout=15) as c:
        yield c


@pytest.fixture(scope="session")
def anon(base_url):
    with httpx.Client(base_url=base_url, timeout=15) as c:
        yield c
