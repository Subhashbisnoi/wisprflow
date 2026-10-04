import uuid

import jwt
from fastapi.testclient import TestClient

from app.core.container import Container
from tests.conftest import signup


def test_signup_creates_company_and_admin(client: TestClient) -> None:
    data = signup(client)
    assert data["user"]["role"] == "admin"
    assert data["company"]["name"] == "Demo Manufacturing Pvt Ltd"
    assert data["company"]["state_code"] == "27"
    me = client.get("/api/v1/auth/me", headers=data["headers"])
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "priya@acmedemo.in"


def test_signup_duplicate_email_conflicts(client: TestClient) -> None:
    signup(client)
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Other Co",
            "full_name": "Someone",
            "email": "PRIYA@acmedemo.in",
            "password": "another-pass-1",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_signup_validates_input_with_consistent_error_shape(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "X",
            "full_name": "Y",
            "email": "bad",
            "password": "short",
            "company_gstin": "27AAPFU0939F1Z9",
        },
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["request_id"]
    fields = {d["field"] for d in error["details"]}
    assert {"email", "password", "company_gstin"} <= fields


def test_login_success_and_failure(client: TestClient) -> None:
    signup(client)
    ok = client.post(
        "/api/v1/auth/login", json={"email": "priya@acmedemo.in", "password": "correct-horse-1"}
    )
    assert ok.status_code == 200 and ok.json()["access_token"]
    bad = client.post("/api/v1/auth/login", json={"email": "priya@acmedemo.in", "password": "nope"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_credentials"
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "ghost@nowhere.in", "password": "nope"}
    )
    assert unknown.json()["error"]["code"] == "invalid_credentials"


def test_missing_expired_and_tampered_tokens(client: TestClient, container: Container) -> None:
    data = signup(client)
    assert client.get("/api/v1/invoices").json()["error"]["code"] == "not_authenticated"

    expired = jwt.encode(
        {"sub": data["user"]["id"], "cid": data["company"]["id"], "exp": 1},
        container.settings.jwt_secret_value,
        "HS256",
    )
    response = client.get("/api/v1/invoices", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_expired"

    tampered = data["access_token"][:-3] + "abc"
    response = client.get("/api/v1/invoices", headers={"Authorization": f"Bearer {tampered}"})
    assert response.json()["error"]["code"] == "invalid_token"


def test_token_for_a_different_company_is_rejected(
    client: TestClient, container: Container
) -> None:
    data = signup(client)
    forged = container.token_service.issue(uuid.UUID(data["user"]["id"]), uuid.uuid4()).token
    response = client.get("/api/v1/invoices", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "trace-123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-123"
