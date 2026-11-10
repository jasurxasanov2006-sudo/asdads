from fastapi.testclient import TestClient

import main


def test_upload_summary_stats_clean_and_undo(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    main.FILES.clear()
    client = TestClient(main.app)
    content = b"name,amount\nAli,10\nVali,\nAli,10\n"

    uploaded = client.post(
        "/upload",
        files={"file": ("sample.csv", content, "text/csv")},
    )
    assert uploaded.status_code == 200
    file_id = uploaded.json()["file_id"]

    assert client.get(f"/files/{file_id}/summary").status_code == 200
    assert client.get(f"/files/{file_id}/stats").status_code == 200
    assert client.get(f"/files/{file_id}/report.html").status_code == 200
    assert client.get(f"/files/{file_id}/download.xlsx").status_code == 200

    cleaned = client.post(
        f"/files/{file_id}/clean",
        json={"actions": [{"type": "remove_duplicates"}]},
    )
    assert cleaned.status_code == 200
    assert cleaned.json()["after"]["rows"] == 2
    assert client.post(f"/files/{file_id}/undo").json()["undone"]
    main.FILES.clear()


def test_sql_endpoint_rejects_mutation_and_runs_select(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    main.FILES.clear()
    client = TestClient(main.app)
    uploaded = client.post(
        "/upload",
        files={"file": ("sample.csv", b"name,amount\nAli,10\nVali,20\n", "text/csv")},
    )
    file_id = uploaded.json()["file_id"]

    assert client.post("/sql", json={"sql": "DELETE FROM data"}).status_code == 400
    result = client.post(
        "/sql",
        json={"sql": "SELECT COUNT(*) AS n FROM data", "active_id": file_id},
    )
    assert result.status_code == 200
    assert result.json()["rows"] == [[2]]
    main.FILES.clear()


def test_outlier_preview_does_not_save_a_version(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    main.FILES.clear()
    client = TestClient(main.app)
    uploaded = client.post(
        "/upload",
        files={"file": ("values.csv", b"value\n1\n2\n3\n4\n5\n100\n", "text/csv")},
    )
    file_id = uploaded.json()["file_id"]

    preview = client.post(
        f"/files/{file_id}/outliers",
        json={"column": "value", "k": 1.5, "action": "preview"},
    )

    assert preview.status_code == 200
    assert preview.json()["count"] == 1
    assert len(main.FILES[file_id]["versions"]) == 1
    main.FILES.clear()


def test_clean_dry_run_recipe_reapply_mismatch_and_undo(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    main.FILES.clear()
    client = TestClient(main.app)
    uploaded = client.post(
        "/upload",
        files={"file": ("sample.csv", b"name,amount,note\nAli,10,\nVali,20,ok\n", "text/csv")},
    )
    file_id = uploaded.json()["file_id"]

    dry_run = client.post(
        f"/files/{file_id}/clean",
        json={
            "dry_run": True,
            "actions": [{"type": "rename_column", "column": "amount", "new_name": "total"}],
        },
    )
    assert dry_run.status_code == 200
    assert dry_run.json()["before"]["preview"][0]["amount"] == "10"
    assert dry_run.json()["after"]["preview"][0]["total"] == "10"
    assert len(main.FILES[file_id]["versions"]) == 1

    saved = client.post(
        "/recipes",
        json={
            "name": "Ustun nomini almashtirish",
            "actions": [{"type": "rename_column", "column": "amount", "new_name": "total"}],
        },
    )
    assert saved.status_code == 200
    recipe_id = saved.json()["id"]
    assert client.get("/recipes").json()[0]["id"] == recipe_id

    applied = client.post(f"/files/{file_id}/apply_recipe/{recipe_id}", json={})
    assert applied.status_code == 200
    assert "total" in applied.json()["preview"][0]
    assert len(main.FILES[file_id]["versions"]) == 2
    undone = client.post(f"/files/{file_id}/undo")
    assert undone.status_code == 200
    assert "amount" in undone.json()["preview"][0]

    invalid_recipe = client.post(
        "/recipes",
        json={
            "name": "Ikkinchi qadamda xato",
            "actions": [
                {"type": "rename_column", "column": "amount", "new_name": "temporary"},
                {"type": "rename_column", "column": "topilmadi", "new_name": "other"},
            ],
        },
    )
    failed = client.post(
        f"/files/{file_id}/apply_recipe/{invalid_recipe.json()['id']}",
        json={},
    )
    assert failed.status_code == 400
    assert "2-qadami" in failed.json()["detail"]
    assert len(main.FILES[file_id]["versions"]) == 1
    assert "amount" in main.FILES[file_id]["versions"][0]["df"].columns

    other_upload = client.post(
        "/upload",
        files={"file": ("other.csv", b"name,price\nAli,10\n", "text/csv")},
    )
    other_id = other_upload.json()["file_id"]
    mismatch = client.post(f"/files/{other_id}/apply_recipe/{recipe_id}", json={})
    assert mismatch.status_code == 400
    assert "1-qadami" in mismatch.json()["detail"]
    main.FILES.clear()


def test_recipe_rejects_empty_recipe_and_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    client = TestClient(main.app)

    assert client.post("/recipes", json={"name": "Bo'sh", "actions": []}).status_code == 400
    assert client.post("/files/missing/apply_recipe/not-a-recipe-id", json={}).status_code == 404


def test_clean_rejects_empty_action_list(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    main.FILES.clear()
    client = TestClient(main.app)
    uploaded = client.post(
        "/upload",
        files={"file": ("sample.csv", b"name\nAli\n", "text/csv")},
    )
    file_id = uploaded.json()["file_id"]

    response = client.post(f"/files/{file_id}/clean", json={"actions": []})

    assert response.status_code == 400
    assert "Kamida bitta" in response.json()["detail"]
    main.FILES.clear()


def test_near_duplicate_endpoint_reports_and_removes_rows_with_undo(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    main.FILES.clear()
    client = TestClient(main.app)
    uploaded = client.post(
        "/upload",
        files={"file": ("near.csv", b"name,city\n  Ali   Vali ,Toshkent\nali vali,toshkent\nBobur,Buxoro\n", "text/csv")},
    )
    file_id = uploaded.json()["file_id"]

    found = client.post(
        f"/files/{file_id}/near_duplicates",
        json={"columns": ["name", "city"]},
    )
    assert found.status_code == 200
    assert found.json()["duplicate_rows"] == 1
    assert found.json()["groups"][0]["rows"] == [2, 3]

    removed = client.post(
        f"/files/{file_id}/clean",
        json={"actions": [{"type": "remove_near_duplicates", "columns": ["name", "city"]}]},
    )
    assert removed.status_code == 200
    assert removed.json()["after"]["rows"] == 2
    assert client.post(f"/files/{file_id}/undo").json()["summary"]["rows"] == 3
    main.FILES.clear()


def test_frontend_assets_and_dashboard_routes_are_connected():
    client = TestClient(main.app)

    assert client.get("/").status_code == 200
    assert client.get("/charts.js").status_code == 200
    assert client.get("/dashboard.js").status_code == 200
    assert client.get("/extras.js").status_code == 200
    assert client.get("/dashboard").status_code == 200
