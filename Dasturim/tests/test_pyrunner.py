import ast
import io
import json
import pickle

import pandas as pd
import pytest

import pyrunner


def _capture_run(monkeypatch, tmp_path, payload):
    payload_path = tmp_path / "payload.pickle"
    payload_path.write_bytes(pickle.dumps(payload))
    output = io.StringIO()
    monkeypatch.setattr(pyrunner.sys, "argv", ["pyrunner.py", str(payload_path)])
    monkeypatch.setattr(pyrunner.sys, "__stdout__", output)
    pyrunner.run()
    return json.loads(output.getvalue().split(pyrunner.MARKER, 1)[1])


def test_policy_rejects_file_access_and_unapproved_imports():
    for code in ("open('secret.txt')", "import os", "import os.path", "import sklearn; model.fit(n_jobs=2)"):
        with pytest.raises(pyrunner.CodePolicyError):
            pyrunner.PolicyVisitor().visit(ast.parse(code))

    pyrunner.PolicyVisitor().visit(ast.parse("import matplotlib"))
    with pytest.raises(ImportError):
        pyrunner.safe_import("os")


def test_result_conversion_handles_series_missing_values_and_limits():
    frame = pd.DataFrame({"value": [1, float("nan"), 3]}, index=[3, 4, 5])
    result = pyrunner.to_table(frame)
    assert result["columns"] == ["index", "value"]
    assert result["rows"] == [[3, 1.0], [4, None], [5, 3.0]]
    assert pyrunner.describe(None) is None
    assert pyrunner.describe(pd.Series([1, 2]))["kind"] == "table"
    assert pyrunner.cell(pd.NA) is None
    assert pyrunner.cell(True) is True
    assert pyrunner.cell(2.34567) == 2.3457
    assert pyrunner.to_table(pd.DataFrame({"x": range(501)}))["truncated"] is True


def test_one_shot_runner_returns_value_and_reports_policy_error(monkeypatch, tmp_path):
    base = {"df": pd.DataFrame({"value": [1]}), "tables": {}, "before": []}
    result = _capture_run(monkeypatch, tmp_path, {**base, "code": "print('hello')\n40 + 2"})
    assert result["stdout"] == "hello\n"
    assert result["result"]["text"] == "42"
    assert result["error"] is None

    blocked = _capture_run(monkeypatch, tmp_path, {**base, "code": "open('secret.txt')"})
    assert "taqiqlangan" in blocked["error"]


def test_persistent_kernel_keeps_variables_between_cells(monkeypatch, tmp_path):
    requests = []
    for code in ("value = 40", "value + 2"):
        payload_path = tmp_path / f"{len(requests)}.pickle"
        payload_path.write_bytes(pickle.dumps({
            "df": pd.DataFrame({"value": [1]}),
            "tables": {},
            "code": code,
        }))
        requests.append(json.dumps({"payload": str(payload_path)}))
    output = io.StringIO()
    monkeypatch.setattr(pyrunner.sys, "stdin", io.StringIO("\n".join(requests) + "\n"))
    monkeypatch.setattr(pyrunner.sys, "__stdout__", output)

    pyrunner.run_kernel()

    first, second = [json.loads(line) for line in output.getvalue().splitlines()]
    assert first["error"] is None
    assert second["result"]["text"] == "42"
    assert second["error"] is None
