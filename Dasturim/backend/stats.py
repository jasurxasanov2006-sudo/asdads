import math

import numpy as np
import pandas as pd

from ai import typed_frame

MAX_NUMERIC_FOR_CORR = 20
TOP_VALUES = 5
BINS = 10


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 4)


def _histogram(s: pd.Series) -> dict:
    counts, edges = np.histogram(s.astype(float), bins=BINS)
    return {"edges": [_num(e) for e in edges], "counts": [int(c) for c in counts]}


def _describe_column(name: str, s: pd.Series, total: int) -> dict:
    missing = int(s.isna().sum())
    info = {
        "name": name,
        "missing": missing,
        "missing_pct": _num(missing * 100 / total) if total else 0,
    }
    valid = s.dropna()

    if pd.api.types.is_numeric_dtype(s.dtype):
        info["type"] = "number"
        if len(valid):
            info.update(
                {
                    "count": int(len(valid)),
                    "unique": int(valid.nunique()),
                    "mean": _num(valid.mean()),
                    "median": _num(valid.median()),
                    "std": _num(valid.std()),
                    "min": _num(valid.min()),
                    "max": _num(valid.max()),
                    "histogram": _histogram(valid),
                }
            )
    elif pd.api.types.is_datetime64_any_dtype(s.dtype):
        info["type"] = "date"
        if len(valid):
            info["min"] = valid.min().strftime("%Y-%m-%d")
            info["max"] = valid.max().strftime("%Y-%m-%d")
    else:
        info["type"] = "text"
        info["unique"] = int(valid.nunique())
        top = valid.astype(str).value_counts().head(TOP_VALUES)
        info["top"] = [{"value": str(k), "count": int(v)} for k, v in top.items()]
    return info


def describe_dataframe(df: pd.DataFrame) -> dict:
    typed = typed_frame(df)
    total = len(typed)
    columns = []
    numeric_idx = []

    for i, col in enumerate(typed.columns):
        name = str(col)
        try:
            info = _describe_column(name, typed.iloc[:, i], total)
        except Exception as e:  # bitta ustun xato bersa, qolganlari ishlayveradi
            info = {
                "name": name,
                "type": "text",
                "missing": 0,
                "missing_pct": 0,
                "unique": 0,
                "top": [],
                "error": f"{type(e).__name__}: {str(e)[:120]}",
            }
        columns.append(info)
        if info.get("type") == "number" and info.get("count"):
            numeric_idx.append(i)

    correlations = []
    idx = numeric_idx[:MAX_NUMERIC_FOR_CORR]
    if len(idx) >= 2 and total >= 10:
        try:
            matrix = typed.iloc[:, idx].corr(numeric_only=True).to_numpy()
            names = [str(typed.columns[i]) for i in idx]
            for a in range(len(idx)):
                for b in range(a + 1, len(idx)):
                    r = _num(matrix[a, b])
                    if r is not None and abs(r) >= 0.3:
                        correlations.append({"a": names[a], "b": names[b], "r": r})
            correlations.sort(key=lambda x: -abs(x["r"]))
        except Exception:
            correlations = []

    return {"rows": total, "columns": columns, "correlations": correlations[:15]}