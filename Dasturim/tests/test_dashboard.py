from fastapi import FastAPI
from fastapi.testclient import TestClient
import pandas as pd

from dashboard import make_router


def test_dashboard_panel_save_run_delete(tmp_path):
    files = {
        "file-id": {
            "table": "sales",
            "versions": [{"df": pd.DataFrame({"category": ["A", "A", "B"], "amount": ["2", "3", "4"]})}],
        }
    }
    app = FastAPI()
    app.include_router(make_router(files, tmp_path))
    client = TestClient(app)

    saved = client.post(
        "/dashboard",
        json={
            "title": "Jami",
            "sql": "SELECT category, SUM(amount) AS total FROM data GROUP BY category ORDER BY category",
            "table": "sales",
            "chart": {"type": "bar"},
        },
    )
    assert saved.status_code == 200, saved.text
    panel_id = saved.json()["id"]

    result = client.post(f"/dashboard/{panel_id}/run")
    assert result.status_code == 200
    assert result.json()["rows"] == [["A", 5], ["B", 4]]
    assert client.get("/dashboard").json()[0]["id"] == panel_id

    assert client.delete(f"/dashboard/{panel_id}").status_code == 200
    assert client.get("/dashboard").json() == []


def test_dashboard_rejects_unsafe_sql(tmp_path):
    app = FastAPI()
    app.include_router(make_router({}, tmp_path))

    response = TestClient(app).post(
        "/dashboard",
        json={"title": "bad", "sql": "DROP TABLE data"},
    )

    assert response.status_code == 400


def test_legacy_per_table_dashboard_api_is_preserved(tmp_path):
    files = {"file-id": {"table": "sales", "versions": []}}
    (tmp_path / "file-id").mkdir()
    app = FastAPI()
    app.include_router(make_router(files, tmp_path))
    client = TestClient(app)

    saved = client.post(
        "/dashboard/file-id",
        json={"title": "Eski panel", "type": "sql", "content": "SELECT 1"},
    )

    assert saved.status_code == 200
    assert client.get("/dashboard/file-id").json()[0]["title"] == "Eski panel"
    assert client.delete("/dashboard/file-id/0").status_code == 200


def test_dashboard_filters_apply_to_panels_and_persist(tmp_path):
    files = {
        "file-id": {
            "table": "sales",
            "versions": [{"df": pd.DataFrame({
                "city": ["A", "A", "B"], "amount": ["2", "3", "7"],
            })}],
        }
    }
    app = FastAPI()
    app.include_router(make_router(files, tmp_path))
    client = TestClient(app)
    panel = client.post(
        "/dashboard",
        json={"title": "Jami", "sql": "SELECT SUM(amount) AS total FROM data", "table": "sales"},
    ).json()

    saved = client.put(
        "/dashboard/filters",
        json={"filters": [{"table": "sales", "column": "city", "kind": "values", "values": ["A"]}]},
    )
    assert saved.status_code == 200
    result = client.post(f"/dashboard/{panel['id']}/run")
    assert result.json()["rows"] == [[5]]
    assert client.get("/dashboard/filters").json()["filters"][0]["values"] == ["A"]

    reopened = FastAPI()
    reopened.include_router(make_router(files, tmp_path))
    assert TestClient(reopened).post(f"/dashboard/{panel['id']}/run").json()["rows"] == [[5]]


def test_dashboard_edit_reorder_grid_and_html_export(tmp_path):
    files = {
        "file-id": {
            "table": "sales",
            "versions": [{"df": pd.DataFrame({"city": ["A"], "amount": ["4"]})}],
        }
    }
    app = FastAPI()
    app.include_router(make_router(files, tmp_path))
    client = TestClient(app)
    first = client.post("/dashboard", json={"title": "Birinchi", "sql": "SELECT * FROM data", "table": "sales"}).json()
    second = client.post("/dashboard", json={"title": "Ikkinchi", "sql": "SELECT * FROM data", "table": "sales"}).json()

    edited = client.put(
        f"/dashboard/panels/{first['id']}",
        json={"title": "KPI", "sql": "SELECT SUM(amount) AS total FROM data", "table": "sales", "kind": "kpi", "grid": {"span": 3}},
    )
    assert edited.status_code == 200
    assert edited.json()["kind"] == "kpi"
    reordered = client.post("/dashboard/reorder", json={"panel_ids": [second["id"], first["id"]]})
    assert [item["id"] for item in reordered.json()] == [second["id"], first["id"]]
    export = client.get("/dashboard/export.html")
    assert export.status_code == 200
    assert "Ikkinchi" in export.text and "KPI" in export.text and "<table>" in export.text


def test_dashboard_date_range_filters_all_saved_panels(tmp_path):
    files = {
        "file-id": {
            "table": "sales",
            "versions": [{"df": pd.DataFrame({
                "day": ["2026-01-01", "2026-02-01", "2026-03-01"],
                "amount": ["2", "3", "7"],
            })}],
        }
    }
    app = FastAPI()
    app.include_router(make_router(files, tmp_path))
    client = TestClient(app)
    panel = client.post(
        "/dashboard",
        json={"title": "Davr", "sql": "SELECT SUM(amount) FROM data", "table": "sales"},
    ).json()
    saved = client.put(
        "/dashboard/filters",
        json={"filters": [{
            "table": "sales", "column": "day", "kind": "date",
            "from": "2026-02-01", "to": "2026-02-28",
        }]},
    )
    assert saved.status_code == 200
    assert client.post(f"/dashboard/{panel['id']}/run").json()["rows"] == [[3]]
