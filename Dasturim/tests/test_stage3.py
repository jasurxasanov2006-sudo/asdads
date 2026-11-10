import json

import pandas as pd
from fastapi.testclient import TestClient

import main


def test_projects_keep_tables_and_dashboards_separate(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    monkeypatch.setattr(main, "ACTIVE_PROJECT_ID", "default")
    main.FILES.clear()
    client = TestClient(main.app)

    first = client.post("/projects", json={"name": "Birinchi loyiha"})
    assert first.status_code == 200
    first_id = first.json()["active_id"]
    uploaded = client.post(
        "/upload",
        files={"file": ("first.csv", b"name,value\nAli,10\n", "text/csv")},
    )
    assert uploaded.status_code == 200
    first_file = uploaded.json()["file_id"]

    second = client.post("/projects", json={"name": "Ikkinchi loyiha"})
    assert second.status_code == 200
    second_id = second.json()["active_id"]
    assert second_id != first_id
    assert client.get("/files").json() == []
    assert client.post(f"/projects/{first_id}/activate").status_code == 200
    assert [row["file_id"] for row in client.get("/files").json()] == [first_file]
    assert client.get("/projects").json()["active_id"] == first_id
    main.FILES.clear()


def test_project_dashboard_and_notebook_cells_are_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    monkeypatch.setattr(main, "ACTIVE_PROJECT_ID", "default")
    main.FILES.clear()
    client = TestClient(main.app, base_url="http://127.0.0.1", client=("127.0.0.1", 8000))

    first = client.post("/projects", json={"name": "A"}).json()["active_id"]
    panel = client.post("/dashboard", json={"title": "Sinov", "sql": "SELECT 1"})
    assert panel.status_code == 200
    notebook = client.post(
        "/py/notebook",
        headers={"X-Dataflow": "1"},
        json={"cells": [{"id": "cell-1", "code": "1 + 1"}]},
    )
    assert notebook.status_code == 200

    second = client.post("/projects", json={"name": "B"}).json()["active_id"]
    assert client.get("/dashboard").json() == []
    assert client.get("/py/notebook", headers={"X-Dataflow": "1"}).json() == []
    assert client.post(f"/projects/{first}/activate").status_code == 200
    assert client.get("/dashboard").json()[0]["title"] == "Sinov"
    assert client.get("/py/notebook", headers={"X-Dataflow": "1"}).json() == [
        {"id": "cell-1", "code": "1 + 1"}
    ]
    assert second != first
    main.FILES.clear()


def test_upload_all_excel_sheets_and_choose_selected_sheets(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    monkeypatch.setattr(main, "ACTIVE_PROJECT_ID", "default")
    main.FILES.clear()
    client = TestClient(main.app)
    excel = tmp_path / "workbook.xlsx"
    with pd.ExcelWriter(excel, engine="openpyxl") as writer:
        pd.DataFrame({"name": ["Ali"], "score": [10]}).to_excel(
            writer, sheet_name="Natijalar", index=False
        )
        pd.DataFrame({"city": ["Toshkent"]}).to_excel(
            writer, sheet_name="Hududlar", index=False
        )
    content = excel.read_bytes()

    sheets = client.post(
        "/upload/sheets",
        files={"file": ("workbook.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert sheets.status_code == 200
    assert sheets.json()["sheets"] == ["Natijalar", "Hududlar"]

    uploaded = client.post(
        "/upload",
        data={"sheets": json.dumps(["__all__"])},
        files={"file": ("workbook.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert uploaded.status_code == 200
    assert [table["filename"] for table in uploaded.json()["tables"]] == [
        "workbook_Natijalar.xlsx",
        "workbook_Hududlar.xlsx",
    ]
    assert len(client.get("/files").json()) == 2
    selected = client.post(
        "/upload",
        data={"sheets": json.dumps(["Hududlar"])},
        files={"file": ("selected.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert selected.status_code == 200
    assert selected.json()["filename"] == "selected_Hududlar.xlsx"
    assert len(client.get("/files").json()) == 3
    main.FILES.clear()


def test_pagination_sort_and_validation_use_parquet(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    monkeypatch.setattr(main, "ACTIVE_PROJECT_ID", "default")
    main.FILES.clear()
    client = TestClient(main.app)
    uploaded = client.post(
        "/upload",
        files={"file": ("values.csv", b"name,value\nAli,3\nVali,1\nBobur,2\n", "text/csv")},
    )
    file_id = uploaded.json()["file_id"]

    page = client.get(f"/files/{file_id}/rows?offset=1&limit=1&sort=value&direction=desc")
    assert page.status_code == 200
    assert page.json()["rows"] == [["Bobur", "2"]]
    assert page.json()["total"] == 3
    assert (tmp_path / "projects" / "default" / "tables" / file_id / "v0.parquet").is_file()
    assert client.get(f"/files/{file_id}/rows?sort=value%22%20DESC%3B%20DROP%20TABLE%20data").status_code == 400
    main.FILES.clear()


def test_legacy_workspace_migrates_csv_versions_into_default_project(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    monkeypatch.setattr(main, "ACTIVE_PROJECT_ID", "default")
    table = tmp_path / "legacy-table"
    table.mkdir()
    (table / "meta.json").write_text(
        json.dumps({"filename": "legacy.csv", "table": "legacy", "labels": ["Asl nusxa"]}),
        encoding="utf-8",
    )
    (table / "v0.csv").write_text("name,value\nAli,10\n", encoding="utf-8")
    (tmp_path / "dashboard.json").write_text("[]", encoding="utf-8")

    main.migrate_workspace()
    main.load_workspace()

    migrated = tmp_path / "projects" / "default" / "tables" / "legacy-table"
    assert (migrated / "v0.parquet").is_file()
    assert not (migrated / "v0.csv").exists()
    assert (tmp_path / "projects" / "default" / "dashboard.json").is_file()
    assert main.FILES["legacy-table"]["versions"][0]["df"].to_dict(orient="records") == [
        {"name": "Ali", "value": "10"}
    ]
    main.FILES.clear()
