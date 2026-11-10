import io
import csv

import pytest
from openpyxl import load_workbook
from fastapi.testclient import TestClient

import ai
import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    monkeypatch.setattr(main, "ACTIVE_PROJECT_ID", main.DEFAULT_PROJECT_ID)
    main.FILES.clear()
    return TestClient(main.app, base_url="http://127.0.0.1", client=("127.0.0.1", 8000))


def upload_csv(client, content, filename="quality.csv"):
    response = client.post(
        "/upload",
        files={"file": (filename, content, "text/csv")},
    )
    assert response.status_code == 200
    return response.json()["file_id"]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; SELECT 2",
        "SELECT * FROM read_csv('/etc/passwd')",
        "COPY (SELECT 1) TO '/tmp/out.csv'",
        "DROP TABLE data",
    ],
)
def test_sql_policy_rejects_multiple_statements_and_file_or_mutation_ops(sql):
    with pytest.raises(ai.AIError):
        ai.check_sql(sql)


def test_sql_policy_allows_keywords_inside_quoted_literals():
    assert ai.check_sql("SELECT 'drop table' AS message") == "SELECT 'drop table' AS message"


def test_upload_limit_and_extension_are_enforced(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_SIZE", 4)
    too_large = client.post(
        "/upload",
        files={"file": ("large.csv", b"a\n12345\n", "text/csv")},
    )
    unsupported = client.post(
        "/upload",
        files={"file": ("payload.txt", b"a\n1\n", "text/plain")},
    )
    assert too_large.status_code == 413
    assert unsupported.status_code == 400


def test_csv_and_excel_exports_neutralize_formula_cells(client):
    file_id = upload_csv(
        client,
        b"label\n=1+1\n@SUM(1)\n-1\n",
        'sample".csv',
    )

    csv_response = client.get(f"/files/{file_id}/download")
    values = list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
    assert values[1:] == [["'=1+1"], ["'@SUM(1)"], ["-1"]]
    assert "\r" not in csv_response.headers["content-disposition"]
    assert "\n" not in csv_response.headers["content-disposition"]
    assert "X-Evil" not in csv_response.headers["content-disposition"]

    xlsx_response = client.get(f"/files/{file_id}/download.xlsx")
    workbook = load_workbook(io.BytesIO(xlsx_response.content), data_only=False)
    cells = [workbook["Ma'lumot"].cell(row, 1) for row in range(2, 5)]
    assert [cell.value for cell in cells] == ["'=1+1", "'@SUM(1)", "-1"]
    assert all(cell.data_type != "f" for cell in cells)


def test_html_report_escapes_untrusted_column_names(client):
    file_id = upload_csv(
        client,
        b'"<img src=x onerror=alert(1)>",amount\nok,1\n',
    )
    response = client.get(f"/files/{file_id}/report.html")
    assert response.status_code == 200
    assert "<img src=x onerror=alert(1)>" not in response.text
    assert "&lt;img" in response.text


def test_saved_report_download_rejects_parent_path(client):
    response = client.get("/reports/saved/..%2F..%2Fauth.sqlite3")
    assert response.status_code in {400, 404}
