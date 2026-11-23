"""오류가 계약서 Problem 형식으로 나가는지 확인한다 (core/errors.py, main.py)."""
import pytest
from fastapi.testclient import TestClient

import db
import main
from core import config

PROBLEM_KEYS = {"type", "title", "status", "detail", "instance", "reason", "trace_id"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "reports.db"))
    db._initialized_paths.clear()
    # raise_server_exceptions=False: 500 응답 본문을 확인하려고 예외를 테스트로 다시 던지지 않게 한다
    return TestClient(main.app, raise_server_exceptions=False)


def _assert_problem(response, status, code):
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert set(body) == PROBLEM_KEYS
    assert body["status"] == status
    assert body["reason"]["code"] == code
    assert body["detail"] == body["reason"]["message"]  # 프런트는 detail을 문구로 읽는다
    assert body["trace_id"] == response.headers["x-trace-id"] != "-"
    return body


def test_missing_job_is_404_problem(client):
    body = _assert_problem(client.get("/debate/jobs/nope"), 404, "job_not_found")
    assert body["reason"]["next_action"] == {"type": "fix_input"}


def test_body_validation_is_422_with_fields(client):
    body = _assert_problem(client.post("/users", json={}), 422, "invalid_request")
    assert body["reason"]["next_action"]["payload"]["fields"] == ["user_id"]


def test_domain_validation_is_422(client):
    _assert_problem(client.post("/users", json={"user_id": "  "}), 422, "invalid_request")


def test_unknown_company_is_company_not_found(client, monkeypatch):
    import processing.functions.resolve_company as rc

    monkeypatch.setattr(rc, "resolve_company", lambda _: {"matched": False, "status": "not_found"})
    body = _assert_problem(
        client.post("/orchestrate/debate", json={"user_id": "u1", "company": "없는회사"}),
        422,
        "company_not_found",
    )
    assert body["reason"]["next_action"] == {"type": "rephrase_company"}


def test_lookup_failure_is_503_not_company_not_found(client, monkeypatch):
    import processing.functions.resolve_company as rc

    monkeypatch.setattr(
        rc, "resolve_company", lambda _: {"matched": False, "error": "company_lookup_unavailable"}
    )
    _assert_problem(
        client.post("/orchestrate/debate", json={"user_id": "u1", "company": "삼성전자"}),
        503,
        "upstream_unavailable",
    )


def test_unexpected_error_hides_internal_message(client, monkeypatch):
    import api.users

    def boom(**_):
        raise RuntimeError("postgres://secret@host")

    monkeypatch.setattr(api.users, "create_user", boom)
    body = _assert_problem(client.post("/users", json={"user_id": "u1"}), 500, "internal_error")
    assert "secret" not in body["detail"]


def test_success_response_carries_trace_id(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-trace-id"]


def test_missing_required_env_stops_startup(monkeypatch):
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="UPSTAGE_API_KEY"):
        config.check_required_env()
