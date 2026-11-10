import ast
import base64
import contextlib
import io
import json
import sys
import time
import traceback

import numpy as np
import pandas as pd
import duckdb

MAX_TEXT = 200_000
MAX_ROWS = 500
MAX_IMAGE_BYTES = 2 * 1024 * 1024


class LimitedBuffer(io.StringIO):
    def write(self, text):
        remaining = MAX_TEXT - self.tell()
        if remaining > 0:
            super().write(str(text)[:remaining])
        return len(text)


def describe(value):
    if value is None:
        return None
    if isinstance(value, pd.Series):
        value = value.to_frame()
    if isinstance(value, pd.DataFrame):
        result = value.copy()
        if not isinstance(result.index, pd.RangeIndex):
            result = result.reset_index()
        result.columns = [str(column) for column in result.columns]
        rows = json.loads(result.head(MAX_ROWS).to_json(orient="values", date_format="iso", default_handler=str))
        return {
            "kind": "table",
            "columns": list(result.columns),
            "rows": rows,
            "total": int(len(result)),
            "truncated": len(result) > MAX_ROWS,
        }
    return {"kind": "text", "text": repr(value)[:10_000]}


def execute(code, namespace, output):
    tree = ast.parse(code, "<cell>", "exec")
    last = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = ast.Expression(tree.body.pop().value)
        ast.fix_missing_locations(last)
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        exec(compile(tree, "<cell>", "exec"), namespace)
        return eval(compile(last, "<cell>", "eval"), namespace) if last is not None else None


def render_figures():
    if "matplotlib.pyplot" not in sys.modules:
        return []
    plt = sys.modules["matplotlib.pyplot"]

    images = []
    for number in plt.get_fignums()[:5]:
        figure = plt.figure(number)
        data = io.BytesIO()
        figure.savefig(data, format="png", dpi=72)
        if data.tell() <= MAX_IMAGE_BYTES:
            images.append(base64.b64encode(data.getvalue()).decode("ascii"))
        plt.close(figure)
    return images


def run_sql(payload):
    connection = duckdb.connect(":memory:")
    try:
        for index, (name, value) in enumerate(payload["frames"].items()):
            frame = pd.DataFrame(value["rows"], columns=value["columns"])
            registered = f"_frame_{index}"
            connection.register(registered, frame)
            safe_name = name.replace('"', '""')
            connection.execute(f'CREATE TABLE "{safe_name}" AS SELECT * FROM {registered}')
            connection.unregister(registered)
        connection.execute("SET enable_external_access=false")
        connection.execute("SET lock_configuration=true")
        cursor = connection.execute(payload["sql"])
        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchmany(payload["limit"] + 1)
        truncated = len(rows) > payload["limit"]
        def serialize(value):
            if value is None:
                return None
            if isinstance(value, (float, np.floating)):
                return None if np.isnan(value) else round(float(value), 4)
            if hasattr(value, "as_tuple"):
                return round(float(value), 4)
            if isinstance(value, (int, bool, str)):
                return value
            return str(value)

        rows = [[serialize(value) for value in row] for row in rows[:payload["limit"]]]
        return {"columns": columns, "rows": rows, "truncated": truncated}
    finally:
        connection.close()


def main():
    started = time.monotonic()
    try:
        payload = json.load(sys.stdin)
        if payload.get("kind") == "sql":
            try:
                response = run_sql(payload)
            except Exception as exception:
                response = {"error": f"{type(exception).__name__}: {exception}"[:500]}
            print(json.dumps(response, ensure_ascii=False))
            return
        frames = {
            name: pd.DataFrame(value["rows"], columns=value["columns"])
            for name, value in payload["frames"].items()
        }
        namespace = {"pd": pd, "np": np, "tables": frames, "df": frames[payload["active"]], "__name__": "__main__"}
        codes = payload["codes"]
        output = LimitedBuffer()
        result = None
        error = None
        for index, code in enumerate(codes):
            current_output = output if index == len(codes) - 1 else LimitedBuffer()
            try:
                result = execute(code, namespace, current_output)
            except BaseException as exception:
                label = "Shu katak" if index == len(codes) - 1 else f"{index + 1}-katak (yuqoridagi)"
                error = f"{label}: {type(exception).__name__}: {exception}"
                break
        try:
            described = describe(result)
        except Exception as exception:
            described = {"kind": "text", "text": f"Natijani ko'rsatib bo'lmadi: {type(exception).__name__}: {exception}"}
        response = {
            "stdout": output.getvalue(),
            "result": described,
            "error": error,
            "images": render_figures() if not error else [],
            "seconds": round(time.monotonic() - started, 3),
        }
        rendered = json.dumps(response, ensure_ascii=False)
        if len(rendered.encode("utf-8")) > 12 * 1024 * 1024:
            response["images"] = []
            response["stdout"] = response["stdout"][:20_000]
            rendered = json.dumps(response, ensure_ascii=False)
        print(rendered)
    except BaseException as exception:
        print(json.dumps({
            "stdout": "",
            "result": None,
            "error": f"Sandbox xatosi: {type(exception).__name__}: {exception}",
            "images": [],
            "seconds": round(time.monotonic() - started, 3),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
