import pandas as pd

MIN_SHARE = 0.6  # ustun qiymatlarining kamida 60% i shu turga mos bo'lsa, ustun shu turda
MAX_ROWS_SHOWN = 20
TYPE_SAMPLE_SIZE = 10000


def file_row(index) -> int:
    """DataFrame indeksini fayldagi qator raqamiga aylantiradi (1-qator = sarlavha)."""
    return int(index) + 2


def detect_type(values: pd.Series) -> str:
    if values.empty:
        return "empty"
    if len(values) > TYPE_SAMPLE_SIZE:
        stride = max(1, len(values) // TYPE_SAMPLE_SIZE)
        sample = values.iloc[::stride]
        numeric_share = pd.to_numeric(sample, errors="coerce").notna().mean()
        if numeric_share >= 0.7:
            return "number"
        date_share = pd.to_datetime(
            sample, errors="coerce", format="mixed"
        ).notna().mean()
        if numeric_share < 0.5 and date_share >= 0.7:
            return "date"
        if numeric_share < 0.5 and date_share < 0.5:
            return "text"
    if pd.to_numeric(values, errors="coerce").notna().mean() >= MIN_SHARE:
        return "number"
    if pd.to_datetime(values, errors="coerce", format="mixed").notna().mean() >= MIN_SHARE:
        return "date"
    return "text"


def make_issue(kind, severity, column, rows, message, suggestion, examples=None):
    return {
        "type": kind,
        "severity": severity,
        "column": column,
        "count": len(rows),
        "rows": rows[:MAX_ROWS_SHOWN],
        "examples": examples or [],
        "message": message,
        "suggestion": suggestion,
    }


def profile_dataframe(df: pd.DataFrame) -> dict:
    columns = []
    issues = []

    for col in df.columns:
        series = df[col]
        missing_mask = series.isna() | series.fillna("").astype(str).str.strip().eq("")
        values = series[~missing_mask].astype(str).str.strip()
        kind = detect_type(values)

        missing_rows = [file_row(i) for i in series.index[missing_mask.to_numpy()]]
        columns.append(
            {
                "name": str(col),
                "type": kind,
                "missing": len(missing_rows),
                "unique": int(values.nunique()),
            }
        )

        if missing_rows:
            issues.append(
                make_issue(
                    "missing", "warning", str(col), missing_rows,
                    f"'{col}' ustunida {len(missing_rows)} ta bo'sh qiymat bor",
                    "Bo'sh qiymatlarni to'ldiring yoki qatorni olib tashlang",
                )
            )

        if kind == "number":
            numbers = pd.to_numeric(values, errors="coerce")
            bad = numbers.isna()
            if bad.any():
                bad_rows = [file_row(i) for i in values.index[bad.to_numpy()]]
                issues.append(
                    make_issue(
                        "invalid_number", "error", str(col), bad_rows,
                        f"'{col}' ustunida {len(bad_rows)} ta raqam bo'lmagan qiymat bor",
                        "Qiymatni to'g'rilang yoki bo'sh qoldiring",
                        [str(v) for v in values[bad].unique()[:5]],
                    )
                )

            nums = numbers.dropna()
            if len(nums) >= 8 and nums.nunique() > 20:
                q1, q3 = nums.quantile(0.25), nums.quantile(0.75)
                iqr = q3 - q1
                if iqr > 0:
                    out = nums[(nums < q1 - 3 * iqr) | (nums > q3 + 3 * iqr)]
                    if not out.empty:
                        out_rows = [file_row(i) for i in out.index]

                        issues.append(
                            make_issue(
                                "outlier", "info", str(col), out_rows,
                                f"'{col}' ustunida {len(out_rows)} ta g'ayritabiiy qiymat bor",
                                "Bu qiymatlar to'g'ri yoki xato ekanini tekshiring",
                                [float(v) for v in out.head(5)],
                            )
                        )

        if kind == "date":
            parsed = pd.to_datetime(values, errors="coerce", format="mixed")
            bad = parsed.isna()
            if bad.any():
                bad_rows = [file_row(i) for i in values.index[bad.to_numpy()]]
                issues.append(
                    make_issue(
                        "invalid_date", "error", str(col), bad_rows,
                        f"'{col}' ustunida {len(bad_rows)} ta noto'g'ri sana bor",
                        "Sanani to'g'rilang (masalan, 2026-01-31)",
                        [str(v) for v in values[bad].unique()[:5]],
                    )
                )

    dup_rows = [file_row(i) for i in df.index[df.duplicated(keep="first").to_numpy()]]
    if dup_rows:
        issues.append(
            make_issue(
                "duplicate", "warning", None, dup_rows,
                f"{len(dup_rows)} ta takroriy qator bor",
                "Takroriy qatorlarni olib tashlang",
            )
        )

    return {
        "summary": {"rows": len(df), "columns": len(df.columns), "issues": len(issues)},
        "columns": columns,
        "issues": issues,
    }