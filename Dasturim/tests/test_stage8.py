import io
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import ai
import main
import security
from pycells import RunRequest, run_in_sandbox


@pytest.fixture
def secured_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFLOW_AUTH_ENABLED", "true")
    monkeypatch.setenv("DATAFLOW_AUTH_DB", str(tmp_path / "auth.sqlite3"))
    monkeypatch.delenv("DATAFLOW_BOOTSTRAP_TOKEN", raising=False)
    monkeypatch.setattr(main, "WORKSPACE", tmp_path / "workspace")
    main.WORKSPACE.mkdir()
    main._USER_FILES.clear()
    main._LOADED_USERS.clear()
    main.ACTIVE_PROJECT_ID = main.DEFAULT_PROJECT_ID
    with security.RATE_LOCK:
        security.RATE_BUCKETS.clear()
    return TestClient(
        main.app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 8200),
    )


def create_admin(client):
    setup = client.post(
        "/auth/setup",
        json={"username": "admin-user", "password": "Strong-Admin-Pass-1"},
    )
    assert setup.status_code == 200
    response = client.post(
        "/auth/login",
        json={"username": "admin-user", "password": "Strong-Admin-Pass-1"},
    )
    assert response.status_code == 200
    return response.json()["user"], response.json()["csrf_token"]


def test_auth_setup_csrf_and_first_admin_owns_existing_workspace(secured_client, tmp_path):
    assert secured_client.get("/projects").status_code == 503
    user, csrf = create_admin(secured_client)

    assert secured_client.get("/projects").status_code == 200
    marker = json.loads((tmp_path / "workspace" / "workspace_owner.json").read_text())
    assert marker["user_id"] == user["id"]
    assert secured_client.post("/projects", json={"name": "No token"}).status_code == 403

    created = secured_client.post(
        "/projects",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Authenticated project"},
    )
    assert created.status_code == 200
    assert any(project["name"] == "Authenticated project" for project in created.json()["projects"])


def test_users_have_isolated_workspaces_and_role_enforcement(secured_client):
    admin, csrf = create_admin(secured_client)
    uploaded = secured_client.post(
        "/upload",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("admin.csv", b"value\n11\n", "text/csv")},
    )
    assert uploaded.status_code == 200

    created = secured_client.post(
        "/auth/users",
        headers={"X-CSRF-Token": csrf},
        json={"username": "viewer-user", "password": "Strong-Viewer-Pass-1", "role": "viewer"},
    )
    assert created.status_code == 200
    assert len(secured_client.get("/files").json()) == 1

    viewer = TestClient(
        main.app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 8201),
    )
    login = viewer.post(
        "/auth/login",
        json={"username": "viewer-user", "password": "Strong-Viewer-Pass-1"},
    )
    assert login.status_code == 200
    assert viewer.get("/files").json() == []
    assert viewer.get("/auth/audit").status_code == 403
    assert viewer.post("/projects", json={"name": "Blocked"}).status_code == 403

    forbidden = secured_client.patch(
        f"/auth/users/{admin['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"role": "viewer"},
    )
    assert forbidden.status_code == 400


def test_sandbox_dispatch_isolated_for_python_and_sql(monkeypatch):
    monkeypatch.setenv("DATAFLOW_PYTHON_SANDBOX", "docker")
    monkeypatch.setenv("DATAFLOW_PYTHON_SANDBOX_URL", "http://sandbox-controller:8787/run")
    monkeypatch.setenv("DATAFLOW_SANDBOX_TOKEN", "test-sandbox-token-with-more-than-32-characters")
    calls = []

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.close()

    def fake_open(request, timeout):
        calls.append(json.loads(request.data))
        if calls[-1].get("kind") == "sql":
            result = {"columns": ["value"], "rows": [[11]], "truncated": False}
        else:
            result = {"stdout": "", "result": None, "error": None, "images": [], "seconds": 0.02}
        return FakeResponse(json.dumps(result).encode())

    monkeypatch.setattr(ai.urllib.request, "urlopen", fake_open)
    frame = pd.DataFrame({"value": [11]})

    assert ai.run_query_tables({"data": frame}, "SELECT * FROM data", 10) == (
        ["value"], [[11]], False
    )
    python_result = run_in_sandbox(
        frame,
        {"data": frame},
        RunRequest(code="df.head()", active_id="file-id"),
        "1" * 32,
    )
    assert python_result["error"] is None
    assert calls[0]["kind"] == "sql"
    assert calls[0]["frames"]["data"]["rows"] == [[11]]
    assert calls[1]["codes"] == ["df.head()"]


def test_sql_sandbox_errors_are_not_reported_as_success(monkeypatch):
    monkeypatch.setenv("DATAFLOW_PYTHON_SANDBOX", "docker")
    monkeypatch.setenv("DATAFLOW_PYTHON_SANDBOX_URL", "http://sandbox-controller:8787/run")
    monkeypatch.setenv("DATAFLOW_SANDBOX_TOKEN", "test-sandbox-token-with-more-than-32-characters")

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.close()

    monkeypatch.setattr(
        ai.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(b'{"error":"ParserException: bad query"}'),
    )
    with pytest.raises(ai.duckdb.Error, match="SQL xatosi"):
        ai.run_query_tables({"data": pd.DataFrame({"x": [1]})}, "SELECT broken")


def test_remote_requests_fail_closed_without_auth_and_execution_sandbox(secured_client, monkeypatch):
    remote = TestClient(
        main.app,
        base_url="http://dataflow.example",
        client=("203.0.113.10", 8300),
    )
    monkeypatch.setenv("DATAFLOW_AUTH_ENABLED", "false")
    assert remote.get("/projects").status_code == 503

    monkeypatch.setenv("DATAFLOW_AUTH_ENABLED", "true")
    monkeypatch.setenv("DATAFLOW_PYTHON_SANDBOX", "local")
    response = remote.post("/sql", json={"sql": "SELECT 1"})
    assert response.status_code == 503
    assert "Docker sandbox" in response.json()["detail"]
