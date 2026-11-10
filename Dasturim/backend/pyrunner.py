import ast
import contextlib
import io
import json
import pickle
import sys
import traceback
import base64
import importlib
import time

import numpy as np
import pandas as pd

MAX_ROWS = 500
MAX_TEXT = 20000
MARKER = "@@RESULT@@"
MAX_IMAGES = 8
MAX_IMAGE_BYTES = 2 * 1024 * 1024

ALLOWED_IMPORTS = {
    "matplotlib",
    "matplotlib.pyplot",
    "sklearn",
    "sklearn.cluster",
    "sklearn.compose",
    "sklearn.ensemble",
    "sklearn.impute",
    "sklearn.linear_model",
    "sklearn.metrics",
    "sklearn.model_selection",
    "sklearn.pipeline",
    "sklearn.preprocessing",
    "sklearn.tree",
}
BLOCKED_NAMES = {
    "__builtins__", "__import__", "breakpoint", "compile", "eval", "exec",
    "getattr", "globals", "input", "locals", "open", "setattr", "delattr",
    "vars", "help",
}
BLOCKED_CALLS = {
    "read_csv", "read_excel", "read_json", "read_parquet", "read_pickle",
    "read_sql", "read_sql_query", "read_sql_table", "read_feather", "read_hdf",
    "read_xml", "read_html", "to_csv", "to_excel", "to_json", "to_parquet",
    "to_pickle", "to_sql", "to_hdf", "to_feather", "to_stata", "to_clipboard",
    "query", "eval", "system", "popen", "spawn", "fork", "fromfile", "memmap",
    "load", "save", "dump", "loadtxt", "savetxt", "ExcelFile", "savefig",
    "listdir", "scandir", "walk", "stat", "unlink", "remove", "mkdir",
    "makedirs", "rmdir", "rename", "replace", "chmod", "chdir", "getcwd",
    "access", "exists", "isfile", "isdir", "readlink", "symlink", "link",
    "truncate", "sendfile", "connect", "create_connection", "urlopen", "request",
    "socket", "Popen", "run", "call", "check_call", "check_output",
    "startfile", "fork_exec", "kill", "terminate", "wait",
}
BLOCKED_ATTRIBUTES = {
    "os", "sys", "subprocess", "socket", "pathlib", "io", "common", "core",
    "compat", "util", "testing", "ctypes", "multiprocessing", "process",
}


class CodePolicyError(ValueError):
    pass


class PolicyVisitor(ast.NodeVisitor):
    def visit_Name(self, node):
        if node.id.startswith("_") or node.id in BLOCKED_NAMES:
            raise CodePolicyError(f"'{node.id}' nomi xavfsizlik sababli taqiqlangan")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if (
            node.attr.startswith("_")
            or node.attr in BLOCKED_CALLS
            or node.attr in BLOCKED_ATTRIBUTES
        ):
            raise CodePolicyError(f"'{node.attr}' atributi xavfsizlik sababli taqiqlangan")
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
            raise CodePolicyError(f"'{node.func.id}' chaqiruvi xavfsizlik sababli taqiqlangan")
        if isinstance(node.func, ast.Attribute) and node.func.attr in BLOCKED_CALLS:
            raise CodePolicyError(f"'{node.func.attr}' chaqiruvi xavfsizlik sababli taqiqlangan")
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name not in ALLOWED_IMPORTS:
                raise CodePolicyError(f"'{alias.name}' importiga ruxsat yo'q")

    def visit_ImportFrom(self, node):
        if node.level or node.module not in ALLOWED_IMPORTS:
            raise CodePolicyError(f"'{node.module}' importiga ruxsat yo'q")

    def visit_Global(self, node):
        raise CodePolicyError("'global' operatoridan foydalanmang")

    def visit_Nonlocal(self, node):
        raise CodePolicyError("'nonlocal' operatoridan foydalanmang")

    def visit_keyword(self, node):
        if node.arg == "n_jobs":
            raise CodePolicyError("'n_jobs' sozlamasi bilan boshqa jarayonlar ishga tushirilishi mumkin emas")
        self.generic_visit(node)


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name not in ALLOWED_IMPORTS:
        raise ImportError(f"'{name}' importiga ruxsat yo'q")
    return importlib.import_module(name)


def safe_namespace(payload):
    allowed = {
        "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
        "enumerate": enumerate, "filter": filter, "float": float, "int": int,
        "isinstance": isinstance, "iter": iter, "len": len, "list": list,
        "map": map, "max": max, "min": min, "next": next, "print": print,
        "range": range, "repr": repr, "reversed": reversed, "round": round,
        "set": set, "slice": slice, "sorted": sorted, "str": str, "sum": sum,
        "tuple": tuple, "zip": zip, "Exception": Exception, "ValueError": ValueError,
        "TypeError": TypeError, "KeyError": KeyError, "IndexError": IndexError,
        "ZeroDivisionError": ZeroDivisionError, "RuntimeError": RuntimeError,
        "float_info": None, "__import__": safe_import,
    }
    return {
        "__builtins__": allowed,
        "__name__": "__main__",
        "pd": pd,
        "np": np,
        "df": payload["df"],
        "tables": payload["tables"],
    }


def render_figures():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    images = []
    for number in plt.get_fignums()[:MAX_IMAGES]:
        buffer = io.BytesIO()
        plt.figure(number).savefig(buffer, format="png", bbox_inches="tight")
        data = buffer.getvalue()
        if len(data) <= MAX_IMAGE_BYTES:
            images.append(base64.b64encode(data).decode("ascii"))
        plt.close(number)
    return images


def cell(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return round(float(v), 4)
    return str(v)


def to_table(obj):
    if isinstance(obj, pd.Series):
        obj = obj.to_frame()
    obj = obj.copy()
    if not isinstance(obj.index, pd.RangeIndex):
        try:
            obj = obj.reset_index()
        except Exception:
            obj = obj.reset_index(drop=True)
    obj.columns = [str(c) for c in obj.columns]
    total = len(obj)
    rows = [
        [cell(v) for v in row]
        for row in obj.head(MAX_ROWS).itertuples(index=False, name=None)
    ]
    return {
        "kind": "table",
        "columns": list(obj.columns),
        "rows": rows,
        "total": int(total),
        "truncated": total > MAX_ROWS,
    }


def describe(result):
    if result is None:
        return None
    if isinstance(result, (pd.DataFrame, pd.Series)):
        return to_table(result)
    return {"kind": "text", "text": repr(result)[:MAX_TEXT]}


def label(filename):
    if filename == "<cell>":
        return "Shu katak"
    num = filename.strip("<>").replace("cell", "").strip()
    return f"{num}-katak (yuqoridagi)"


def fmt_error(e, sources, stage):
    if isinstance(e, SyntaxError):
        text = (e.text or "").strip()
        return f"{stage}: sintaksis xatosi ({e.lineno}-qator): {e.msg}\n{text}"
    lines = []
    for f in traceback.extract_tb(e.__traceback__):
        if not f.filename.startswith("<cell"):
            continue
        src = sources.get(f.filename, [])
        text = src[f.lineno - 1].strip() if 0 < f.lineno <= len(src) else ""
        lines.append(f"{label(f.filename)}, {f.lineno}-qator: {text}")
    lines.append(f"{type(e).__name__}: {e}")
    return "\n".join(lines)


def run():
    with open(sys.argv[1], "rb") as fh:
        payload = pickle.load(fh)

    ns = safe_namespace(payload)
    sources = {}
    out = io.StringIO()
    result = None
    error = None
    stage = "Shu katak"

    try:
        for i, code in enumerate(payload["before"]):
            name = f"<cell {i + 1}>"
            stage = f"{i + 1}-katak (yuqoridagi)"
            sources[name] = code.splitlines()
            PolicyVisitor().visit(ast.parse(code, name, "exec"))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                exec(compile(code, name, "exec"), ns)

        stage = "Shu katak"
        code = payload["code"]
        sources["<cell>"] = code.splitlines()
        tree = ast.parse(code, "<cell>", "exec")
        PolicyVisitor().visit(tree)
        last = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last = ast.Expression(tree.body.pop().value)
            ast.fix_missing_locations(last)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            exec(compile(tree, "<cell>", "exec"), ns)
            if last is not None:
                result = eval(compile(last, "<cell>", "eval"), ns)
    except BaseException as e:
        error = fmt_error(e, sources, stage)

    try:
        res = describe(result)
    except Exception as e:
        res = {"kind": "text", "text": f"Natijani ko'rsatib bo'lmadi: {type(e).__name__}: {e}"}

    data = {"stdout": out.getvalue()[:MAX_TEXT], "result": res, "error": error}
    sys.__stdout__.write("\n" + MARKER + json.dumps(data, ensure_ascii=False) + "\n")
    sys.__stdout__.flush()


def run_kernel():
    ns = None
    for line in sys.stdin:
        started = time.perf_counter()
        try:
            request = json.loads(line)
            with open(request["payload"], "rb") as fh:
                payload = pickle.load(fh)
            if ns is None:
                ns = safe_namespace(payload)
            else:
                ns["df"] = payload["df"]
                ns["tables"] = payload["tables"]

            code = payload["code"]
            out = io.StringIO()
            result = None
            error = None
            try:
                tree = ast.parse(code, "<cell>", "exec")
                PolicyVisitor().visit(tree)
                last = None
                if tree.body and isinstance(tree.body[-1], ast.Expr):
                    last = ast.Expression(tree.body.pop().value)
                    ast.fix_missing_locations(last)
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                    exec(compile(tree, "<cell>", "exec"), ns)
                    if last is not None:
                        result = eval(compile(last, "<cell>", "eval"), ns)
                images = render_figures()
            except BaseException as e:
                error = fmt_error(e, {"<cell>": code.splitlines()}, "Shu katak")
                images = []
            response = {
                "stdout": out.getvalue()[:MAX_TEXT],
                "result": describe(result),
                "error": error,
                "images": images,
                "seconds": round(time.perf_counter() - started, 3),
            }
        except BaseException as e:
            response = {
                "stdout": "",
                "result": None,
                "error": f"{type(e).__name__}: {str(e)[:500]}",
                "images": [],
                "seconds": round(time.perf_counter() - started, 3),
            }
        sys.__stdout__.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.__stdout__.flush()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--kernel":
        run_kernel()
    else:
        run()