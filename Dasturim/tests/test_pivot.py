from fastapi.testclient import TestClient

import main


def test_pivot_groups_cross_tab_and_totals(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    monkeypatch.setattr(main, "ACTIVE_PROJECT_ID", "default")
    main.FILES.clear()
    client = TestClient(main.app)
    uploaded = client.post(
        "/upload",
        files={
            "file": (
                "sales.csv",
                b"city,kind,amount\nA,X,2\nA,Y,3\nB,X,7\n",
                "text/csv",
            )
        },
    )
    file_id = uploaded.json()["file_id"]

    pivot = client.post(
        f"/files/{file_id}/pivot",
        json={"rows": ["city"], "columns": ["kind"], "values": "amount", "aggregation": "sum"},
    )
    assert pivot.status_code == 200
    result = pivot.json()
    assert result["rows"][-1][0] == "Jami"
    assert "X" in result["columns"] and "Y" in result["columns"]
    assert result["rows"][-1][-1] == "12"

    grouped = client.post(
        f"/files/{file_id}/pivot",
        json={"rows": ["city"], "values": "amount", "aggregation": "mean"},
    )
    assert grouped.status_code == 200
    assert grouped.json()["rows"][-1][0] == "Jami"
    main.FILES.clear()


def test_pivot_rejects_bad_columns_and_non_numeric_sum(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    monkeypatch.setattr(main, "ACTIVE_PROJECT_ID", "default")
    main.FILES.clear()
    client = TestClient(main.app)
    uploaded = client.post(
        "/upload",
        files={"file": ("sample.csv", b"group,value\nA,text\n", "text/csv")},
    )
    file_id = uploaded.json()["file_id"]
    bad_column = client.post(
        f"/files/{file_id}/pivot",
        json={"rows": ["missing"], "values": "value"},
    )
    assert bad_column.status_code == 400
    non_numeric = client.post(
        f"/files/{file_id}/pivot",
        json={"rows": ["group"], "values": "value", "aggregation": "sum"},
    )
    assert non_numeric.status_code == 400
    main.FILES.clear()
