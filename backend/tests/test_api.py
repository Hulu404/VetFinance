from fastapi.testclient import TestClient

from tests.conftest import FakeRepo, make_token


def auth(token: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token or make_token()}"}


def test_healthz_is_public(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_no_token_returns_contract_error(client: TestClient) -> None:
    r = client.get("/v1/clinic")
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["code"] == "unauthorized"
    assert set(body["error"]) == {"code", "message", "details"}


def test_bad_signature_and_expired_and_audience(client: TestClient) -> None:
    for token in (
        make_token(secret="x" * 40),
        make_token(exp_delta=-10),
        make_token(aud="other"),
        "garbage",
    ):
        r = client.get("/v1/accounts", headers=auth(token))
        assert r.status_code == 401, token
        assert r.json()["error"]["code"] == "unauthorized"


def test_get_clinic(client: TestClient) -> None:
    r = client.get("/v1/clinic", headers=auth())
    assert r.status_code == 200
    assert r.json()["name"] == "Клиника A"
    assert r.json()["safe_balance"] == 0


def test_patch_clinic(client: TestClient, repo: FakeRepo) -> None:
    r = client.patch(
        "/v1/clinic",
        headers=auth(),
        json={"safe_balance": 15_000_000, "timezone": "Asia/Yekaterinburg"},
    )
    assert r.status_code == 200
    assert r.json()["safe_balance"] == 15_000_000
    assert repo.clinic.timezone == "Asia/Yekaterinburg"


def test_patch_clinic_validation(client: TestClient) -> None:
    for body in ({"safe_balance": -1}, {"safe_balance": 1.5}, {"timezone": "Mars/Base"}, {"x": 1}):
        r = client.patch("/v1/clinic", headers=auth(), json=body)
        assert r.status_code == 422, body
        assert r.json()["error"]["code"] == "validation"


def test_accounts(client: TestClient) -> None:
    r = client.get("/v1/accounts", headers=auth())
    items = r.json()["items"]
    assert [a["kind"] for a in items] == ["bank", "cash"]
    assert r.json()["next_cursor"] is None


def test_dashboard_stage0_shape(client: TestClient) -> None:
    r = client.get("/v1/dashboard", headers=auth())
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"as_of", "data_as_of", "balance"}
    assert set(body["balance"]) == {"total", "bank"}
    assert body["balance"]["total"]["value"] == 9_500_000
    assert body["balance"]["bank"]["value"] == 9_000_000
    assert body["balance"]["total"]["unit"] == "rub"
    assert len(body["balance"]["total"]["breakdown"]) == 2
    assert body["balance"]["total"]["source"] == ["bank"]


def test_cors_preflight(client: TestClient) -> None:
    r = client.options(
        "/v1/clinic",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
