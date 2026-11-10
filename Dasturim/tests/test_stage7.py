import base64
import io

import pandas as pd
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from PIL import Image

import main
import extras


_logo = io.BytesIO()
Image.new("RGB", (1, 1), "white").save(_logo, format="PNG")
LOGO_PNG = f"data:image/png;base64,{base64.b64encode(_logo.getvalue()).decode('ascii')}"


def setup_report_client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    monkeypatch.setattr(main, "ACTIVE_PROJECT_ID", "default")
    main.FILES.clear()
    client = TestClient(main.app, base_url="http://127.0.0.1", client=("127.0.0.1", 8000))
    uploaded = client.post(
        "/upload",
        files={
            "file": (
                "marketing-finance.csv",
                (
                    "customer,date,amount,debit,credit,user,stage,campaign,spend,conversions,reference\n"
                    "Ali,2026-01-03,100,100,100,u1,visit,A,20,2,x1\n"
                    "Ali,2026-02-05,150,150,150,u1,buy,A,30,3,x2\n"
                    "Vali,2026-02-06,120,120,110,u2,visit,B,15,1,x3\n"
                    "Vali,2026-02-06,120,120,110,u2,visit,B,15,1,x3\n"
                ).encode(),
                "text/csv",
            )
        },
    )
    assert uploaded.status_code == 200
    return client, uploaded.json()["file_id"]


def test_report_xlsx_contains_data_stats_issues_and_chart(tmp_path, monkeypatch):
    client, file_id = setup_report_client(tmp_path, monkeypatch)
    try:
        response = client.get(f"/files/{file_id}/download.xlsx")
        assert response.status_code == 200
        workbook = load_workbook(io.BytesIO(response.content))
        assert set(workbook.sheetnames) == {"Ma'lumot", "Umumiy", "Statistika", "Muammolar", "Grafiklar"}
        assert workbook["Ma'lumot"].max_row == 5
        assert isinstance(workbook["Ma'lumot"]["C2"].value, (int, float))
        assert workbook["Statistika"].max_row > 1
        assert workbook["Muammolar"].max_row > 1
        assert len(workbook["Grafiklar"]._charts) == 1
    finally:
        main.FILES.clear()


def test_report_settings_title_logo_pdf_print_and_saved_files(tmp_path, monkeypatch):
    client, file_id = setup_report_client(tmp_path, monkeypatch)
    try:
        headers = {"X-Dataflow": "1"}
        saved = client.put(
            "/report-settings",
            headers=headers,
            json={
                "title": "Oy yakuni",
                "logo": LOGO_PNG,
                "schedule_enabled": True,
                "schedule_time": "03:15",
                "auto_save": True,
            },
        )
        assert saved.status_code == 200
        assert client.get("/report-settings").json()["schedule_time"] == "03:15"
        report = client.get(f"/files/{file_id}/report.html")
        assert "Oy yakuni" in report.text
        assert "window.print()" in report.text
        assert LOGO_PNG in report.text
        excel = client.get(f"/files/{file_id}/download.xlsx")
        workbook = load_workbook(io.BytesIO(excel.content))
        assert len(workbook["Umumiy"]._images) == 1

        updated = client.post("/reports/refresh", headers=headers)
        assert updated.status_code == 200
        files = client.get("/reports/saved").json()
        assert len(files) == 2
        assert {file["name"].rsplit(".", 1)[-1] for file in files} == {"html", "xlsx"}
        saved_xlsx = next(file for file in files if file["name"].endswith(".xlsx"))
        assert client.get(f"/reports/saved/{saved_xlsx['name']}").status_code == 200
    finally:
        main.FILES.clear()


def test_template_gallery_runs_all_marketing_and_finance_examples(tmp_path, monkeypatch):
    client, file_id = setup_report_client(tmp_path, monkeypatch)
    choices = {
        "marketing-rfm": {"customer": "customer", "date": "date", "amount": "amount"},
        "marketing-cohort": {"customer": "customer", "date": "date"},
        "marketing-funnel": {"user": "user", "stage": "stage"},
        "marketing-campaign": {"campaign": "campaign", "spend": "spend", "conversions": "conversions"},
        "finance-balance": {"debit": "debit", "credit": "credit"},
        "finance-duplicates": {"date": "date", "amount": "amount", "reference": "reference"},
        "finance-unusual": {"amount": "amount"},
    }
    try:
        templates = client.get("/templates").json()
        assert {template["id"] for template in templates} == set(choices)
        for template_id, columns in choices.items():
            response = client.post(
                f"/templates/{template_id}/run",
                json={"file_id": file_id, "columns": columns},
            )
            assert response.status_code == 200, (template_id, response.text)
            result = response.json()
            assert "GROUP BY" in result["sql"] or template_id == "finance-balance" or template_id == "finance-unusual"
            if template_id != "finance-unusual":
                assert result["rows"]
            assert "audit" in result["notice"]
            assert result["python"]
    finally:
        main.FILES.clear()


def test_template_column_validation_and_report_settings_reject_bad_inputs(tmp_path, monkeypatch):
    client, file_id = setup_report_client(tmp_path, monkeypatch)
    try:
        invalid = client.post(
            "/templates/marketing-rfm/run",
            json={"file_id": file_id, "columns": {"customer": "amount", "date": "date", "amount": "amount"}},
        )
        assert invalid.status_code == 400
        assert client.put(
            "/report-settings",
            headers={"X-Dataflow": "1"},
            json={"title": "Bad", "logo": "data:image/png;base64,not-an-image"},
        ).status_code == 400
    finally:
        main.FILES.clear()


def test_daily_scheduler_autosaves_reports(tmp_path, monkeypatch):
    client, _ = setup_report_client(tmp_path, monkeypatch)
    monkeypatch.setattr(extras, "SCHEDULER_POLL_SECONDS", 0.05)
    settings = client.get("/report-settings").json()
    settings.update(
        {"schedule_enabled": True, "schedule_time": "00:00", "auto_save": True}
    )
    saved_settings = client.put(
        "/report-settings",
        headers={"X-Dataflow": "1"},
        json=settings,
    )
    assert saved_settings.status_code == 200
    main.FILES.clear()
    try:
        upload = client.post(
            "/upload",
            files={"file": ("scheduled.csv", b"value\n1\n2\n", "text/csv")},
        )
        assert upload.status_code == 200
        with TestClient(
            main.app, base_url="http://127.0.0.1", client=("127.0.0.1", 8000)
        ) as running_client:
            import time

            deadline = time.monotonic() + 5
            reports = []
            while time.monotonic() < deadline:
                reports = running_client.get("/reports/saved").json()
                if len(reports) >= 2:
                    break
                time.sleep(0.05)
            assert {report["name"].rsplit(".", 1)[-1] for report in reports} == {"html", "xlsx"}
    finally:
        main.FILES.clear()
