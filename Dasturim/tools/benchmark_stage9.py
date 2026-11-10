import os
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient


def main():
    os.environ["DATAFLOW_AUTH_ENABLED"] = "false"
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root / "backend"))

    with tempfile.TemporaryDirectory(prefix="dataflow-benchmark-") as directory:
        root = Path(directory)
        os.environ["DATAFLOW_DATA_DIR"] = str(root / "workspace")
        import main as app_module

        app_module.WORKSPACE = root / "workspace"
        app_module.ACTIVE_PROJECT_ID = app_module.DEFAULT_PROJECT_ID
        rows = int(os.getenv("DATAFLOW_BENCHMARK_ROWS", "1000000"))
        csv_path = root / "benchmark.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as output:
            output.write("id,region,amount,description\n")
            for value in range(rows):
                output.write(
                    f"{value},region-{value % 20},{value % 1000},"
                    f"record-{value:07d}-{'x' * 75}\n"
                )

        with TestClient(
            app_module.app,
            base_url="http://127.0.0.1",
            client=("127.0.0.1", 8000),
        ) as client:
            started = time.perf_counter()
            with csv_path.open("rb") as source:
                uploaded = client.post(
                    "/upload",
                    files={"file": (csv_path.name, source, "text/csv")},
                )
            if uploaded.status_code != 200:
                raise RuntimeError(f"Upload failed: {uploaded.status_code} {uploaded.text}")
            opened_seconds = time.perf_counter() - started
            file_id = uploaded.json()["file_id"]

            started = time.perf_counter()
            page = client.get(f"/files/{file_id}/rows?limit=100&offset=0")
            page_seconds = time.perf_counter() - started
            if page.status_code != 200 or len(page.json()["rows"]) != 100:
                raise RuntimeError(f"Pagination failed: {page.status_code} {page.text[:300]}")

            started = time.perf_counter()
            query = client.post(
                "/sql",
                json={"sql": "SELECT COUNT(*) AS row_count FROM data", "active_id": file_id},
            )
            query_seconds = time.perf_counter() - started
            if query.status_code != 200 or query.json()["rows"] != [[rows]]:
                raise RuntimeError(f"SQL benchmark failed: {query.status_code} {query.text[:300]}")

            started = time.perf_counter()
            statistics = client.get(f"/files/{file_id}/stats")
            statistics_seconds = time.perf_counter() - started
            if statistics.status_code != 200:
                raise RuntimeError(f"Statistics failed: {statistics.status_code} {statistics.text[:300]}")

        size_mb = csv_path.stat().st_size / (1024 * 1024)
        print(f"rows={rows:,} file_mb={size_mb:.1f}")
        print(f"open_seconds={opened_seconds:.3f}")
        print(f"page_100_seconds={page_seconds:.3f}")
        print(f"sql_count_seconds={query_seconds:.3f}")
        print(f"statistics_seconds={statistics_seconds:.3f}")

        timings = {
            "open": opened_seconds,
            "page_100": page_seconds,
            "sql_count": query_seconds,
            "statistics": statistics_seconds,
        }
        slow = {name: seconds for name, seconds in timings.items() if seconds >= 10}
        if slow:
            raise SystemExit(f"10-second target missed: {slow}")


if __name__ == "__main__":
    main()
