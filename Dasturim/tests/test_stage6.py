from concurrent.futures import ThreadPoolExecutor
import json
import pickle
import tempfile
import time
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import main
import kernel as kernel_module
from kernel import NotebookKernel
from pycells import KERNELS, close_kernels


def kernel_payload(code, frame=None):
    handle = tempfile.NamedTemporaryFile(prefix="dataflow-test-", suffix=".pkl", delete=False)
    path = Path(handle.name)
    with handle:
        pickle.dump(
            {"code": code, "df": frame or pd.DataFrame({"value": [1, 2]}),
             "tables": {"data": frame or pd.DataFrame({"value": [1, 2]})},
            },
            handle,
        )
    return path


def run_code(kernel, code):
    path = kernel_payload(code)
    try:
        return kernel.run(path)
    finally:
        path.unlink(missing_ok=True)


def test_notebook_kernel_persists_variables_and_restarts():
    kernel = NotebookKernel(Path(main.__file__).parent / "pyrunner.py")
    try:
        assert run_code(kernel, "answer = 40")["error"] is None
        assert run_code(kernel, "answer + 2")["result"]["text"] == "42"
        kernel.restart()
        restarted = run_code(kernel, "answer")
        assert "NameError" in restarted["error"]
    finally:
        kernel.close()


def test_notebook_kernel_blocks_file_access():
    kernel = NotebookKernel(Path(main.__file__).parent / "pyrunner.py")
    try:
        result = run_code(kernel, 'open("private.txt")')
        assert "xavfsizlik sababli taqiqlangan" in result["error"]
    finally:
        kernel.close()


def test_notebook_kernel_timeout_terminates_code(monkeypatch):
    monkeypatch.setattr(kernel_module, "KERNEL_TIMEOUT", 0.25)
    kernel = NotebookKernel(Path(main.__file__).parent / "pyrunner.py")
    try:
        path = kernel_payload("while True:\n    pass")
        try:
            with pytest.raises(TimeoutError, match="to'xtatildi"):
                kernel.run(path)
        finally:
            path.unlink(missing_ok=True)
    finally:
        kernel.close()


def test_notebook_kernel_can_be_interrupted():
    kernel = NotebookKernel(Path(main.__file__).parent / "pyrunner.py")
    path = kernel_payload("while True:\n    pass")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(kernel.run, path)
            deadline = time.monotonic() + 5
            while not kernel.process and time.monotonic() < deadline:
                time.sleep(0.02)
            time.sleep(0.2)
            assert kernel.interrupt()
            with pytest.raises(RuntimeError, match="to'xtadi"):
                running.result(timeout=5)
    finally:
        path.unlink(missing_ok=True)
        kernel.close()


def test_notebook_save_import_and_exports(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORKSPACE", tmp_path)
    main.FILES.clear()
    headers = {"X-Dataflow": "1", "Host": "127.0.0.1"}
    client = TestClient(main.app, client=("127.0.0.1", 12345))
    try:
        upload = client.post(
            "/upload",
            files={"file": ("sample.csv", b"value\n1\n2\n", "text/csv")},
        )
        assert upload.status_code == 200
        active_id = upload.json()["file_id"]
        first = client.post(
            "/py/run", headers=headers,
            json={"code": "persistent_value = 40", "active_id": active_id},
        )
        second = client.post(
            "/py/run", headers=headers,
            json={"code": "persistent_value + 2", "active_id": active_id},
        )
        assert first.status_code == second.status_code == 200
        assert second.json()["result"]["text"] == "42"

        saved = client.post(
            "/py/notebook",
            headers=headers,
            json={"cells": [
                {"id": "code1", "type": "code", "code": "value = 1"},
                {"id": "md1", "type": "markdown", "code": "# Tahlil"},
            ]},
        )
        assert saved.status_code == 200
        assert client.get("/py/notebook", headers=headers).json()[1]["type"] == "markdown"

        py_export = client.get("/py/export.py", headers=headers)
        assert py_export.status_code == 200
        assert "# # Tahlil" in py_export.text

        ipynb_export = client.get("/py/export.ipynb", headers=headers)
        notebook = json.loads(ipynb_export.text)
        assert notebook["nbformat"] == 4
        assert notebook["cells"][1]["cell_type"] == "markdown"

        imported = client.post(
            "/py/import",
            headers=headers,
            files={"file": ("roundtrip.ipynb", ipynb_export.content, "application/json")},
        )
        assert imported.status_code == 200
        assert [cell["type"] for cell in imported.json()["cells"]] == ["code", "markdown"]
        imported_py = client.post(
            "/py/import",
            headers=headers,
            files={"file": ("script.py", b"value = 7\n", "text/x-python")},
        )
        assert imported_py.status_code == 200
        assert imported_py.json()["cells"] == [
            {"id": "imported", "type": "code", "code": "value = 7\n"}
        ]
    finally:
        close_kernels()
        KERNELS.clear()
        main.FILES.clear()
