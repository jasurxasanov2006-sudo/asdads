import pandas as pd

from profiling import detect_type


class CleanError(ValueError):
    """Tozalash amalini bajarib bo'lmaganda ko'tariladi."""


def blank_mask(series: pd.Series) -> pd.Series:
    return series.isna() | series.fillna("").astype(str).str.strip().eq("")


def _column(df: pd.DataFrame, name: str | None) -> str:
    if not name or name not in df.columns:
        raise CleanError(f"Ustun topilmadi: {name}")
    return name


def _check_new_column(df: pd.DataFrame, name: str | None) -> str:
    if not name or not name.strip():
        raise CleanError("Yangi ustun nomini kiriting")
    name = name.strip()
    if name in df.columns:
        raise CleanError(f"'{name}' nomli ustun allaqachon bor")
    return name


def _normalized_key(value) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).split()).casefold()


def near_duplicate_groups(
    df: pd.DataFrame, columns: list[str], row_limit: int | None = 10
) -> list[dict]:
    if not columns:
        raise CleanError("Taqqoslash uchun kamida bitta ustun tanlang")
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise CleanError("Ustun topilmadi: " + ", ".join(missing))

    groups: dict[tuple[str, ...], list[int]] = {}
    for position, row in enumerate(df[columns].itertuples(index=False, name=None)):
        key = tuple(_normalized_key(value) for value in row)
        groups.setdefault(key, []).append(position)

    return [
        {
            "rows": [position + 2 for position in positions[:row_limit]],
            "count": len(positions),
        }
        for positions in groups.values()
        if len(positions) > 1
    ]


def apply_action(df: pd.DataFrame, action) -> tuple[pd.DataFrame, str]:
    kind = action.type
    df = df.copy()

    if kind == "remove_duplicates":
        before = len(df)
        df = df.drop_duplicates(keep="first")
        return df, f"{before - len(df)} ta takroriy qator olib tashlandi"

    if kind == "remove_near_duplicates":
        columns = action.columns or []
        groups = near_duplicate_groups(df, columns, row_limit=None)
        duplicate_positions = {
            row - 2 for group in groups for row in group["rows"][1:]
        }
        df = df.iloc[[i for i in range(len(df)) if i not in duplicate_positions]]
        return df, f"{len(duplicate_positions)} ta deyarli takror qator olib tashlandi"

    if kind == "trim_text":
        changed = 0
        for c in df.columns:
            stripped = df[c].map(lambda v: v.strip() if isinstance(v, str) else v)
            changed += int((df[c].fillna("") != stripped.fillna("")).sum())
            df[c] = stripped
        return df, f"{changed} ta qiymatdagi ortiqcha bo'sh joylar olib tashlandi"

    if kind in {"rename_column", "drop_column", "convert_number", "convert_date", "date_to_iso",
                "split_column", "merge_columns", "replace_values", "fill_missing_unknown",
                "normalize_text"}:
        col = _column(df, action.column) if kind != "merge_columns" else None

        if kind == "rename_column":
            new_name = _check_new_column(df, action.new_name)
            df = df.rename(columns={col: new_name})
            return df, f"'{col}' ustuni '{new_name}' deb nomlandi"

        if kind == "drop_column":
            df = df.drop(columns=[col])
            return df, f"'{col}' ustuni olib tashlandi"

        if kind == "normalize_text":
            mode = action.mode
            if mode not in {"trim", "lower", "upper", "spaces"}:
                raise CleanError("Matn amali: trim, lower, upper yoki spaces bo'lishi kerak")
            source = df[col]
            values = source.map(lambda v: v if pd.isna(v) else str(v))
            if mode == "trim":
                normalized = values.str.strip()
            elif mode == "lower":
                normalized = values.str.lower()
            elif mode == "upper":
                normalized = values.str.upper()
            else:
                normalized = values.str.split().str.join(" ")
            changed = int((source.fillna("") != normalized.fillna("")).sum())
            df[col] = normalized
            labels = {"trim": "chetdagi bo'shliqlar", "lower": "kichik harf", "upper": "katta harf", "spaces": "bo'shliqlar"}
            return df, f"'{col}' ustunida {labels[mode]} normallashtirildi ({changed} ta qiymat)"

        if kind == "fill_missing_unknown":
            blank = blank_mask(df[col])
            count = int(blank.sum())
            fill = action.value or "noma'lum"
            df.loc[blank, col] = fill
            return df, f"'{col}' ustunidagi {count} ta bo'sh qiymat '{fill}' bilan to'ldirildi"

        if kind == "replace_values":
            replacements = action.replacements or {}
            if not replacements:
                raise CleanError("Almashtiriladigan qiymatlar ro'yxatini kiriting")
            source = df[col]
            df[col] = source.replace({str(k): str(v) for k, v in replacements.items()})
            changed = int((source.fillna("") != df[col].fillna("")).sum())
            return df, f"'{col}' ustunida {changed} ta qiymat almashtirildi"

        if kind == "convert_number":
            decimal = action.decimal_separator or "."
            thousands = action.thousands_separator
            if len(decimal) != 1 or (thousands and len(thousands) != 1):
                raise CleanError("Minglik va o'nlik ajratgichlari bittadan belgi bo'lishi kerak")
            if thousands and decimal == thousands:
                raise CleanError("Minglik va o'nlik ajratgichlari har xil bo'lishi kerak")
            source = df[col]
            values = source.astype("string").str.strip()
            values = values.mask(blank_mask(source))
            if thousands:
                values = values.str.replace(thousands, "", regex=False)
            if decimal != ".":
                values = values.str.replace(decimal, ".", regex=False)
            numbers = pd.to_numeric(values, errors="coerce")
            invalid = int((values.notna() & numbers.isna()).sum())
            df[col] = numbers.map(lambda value: None if pd.isna(value) else format(value, "g"))
            return df, f"'{col}' raqamga aylantirildi; {invalid} ta noto'g'ri qiymat bo'sh qoldi"

        if kind in {"convert_date", "date_to_iso"}:
            source = df[col]
            values = source.astype("string").str.strip().mask(blank_mask(source))
            date_format = action.date_format if kind == "convert_date" else None
            try:
                parsed = pd.to_datetime(values, errors="coerce", format=date_format or "mixed")
            except (TypeError, ValueError) as e:
                raise CleanError("Sana formatini tekshiring (masalan, %d/%m/%Y)") from e
            invalid = int((values.notna() & parsed.isna()).sum())
            df[col] = parsed.map(
                lambda value: None if pd.isna(value) else value.strftime("%Y-%m-%d")
            )
            return df, f"'{col}' sana ISO (YYYY-MM-DD) ko'rinishiga o'tkazildi; {invalid} ta noto'g'ri sana bo'sh qoldi"

        if kind == "split_column":
            separator = action.separator
            target = _check_new_column(df, action.new_name)
            if not separator:
                raise CleanError("Bo'lish belgisi (separator) kerak")
            second_name = action.second_column or f"{target}_2"
            _check_new_column(df, second_name)
            parts = df[col].fillna("").astype(str).str.split(separator, n=1, expand=True)
            df[target] = parts[0].str.strip()
            second = parts[1] if parts.shape[1] > 1 else pd.Series("", index=df.index)
            df[second_name] = second.str.strip()
            return df, f"'{col}' ustuni '{target}' va '{second_name}' ustunlariga bo'lindi"

        if kind == "merge_columns":
            columns = action.columns or []
            if len(columns) < 2:
                raise CleanError("Birlashtirish uchun kamida 2 ta ustun tanlang")
            if len(set(columns)) != len(columns):
                raise CleanError("Bir ustunni bir necha marta tanlamang")
            for name in columns:
                _column(df, name)
            target = action.new_name or action.target_column
            if target not in columns:
                target = _check_new_column(df, target)
            separator = action.separator or " "
            values = df[columns].fillna("").astype(str).apply(lambda row: separator.join(
                value.strip() for value in row if value.strip()
            ), axis=1)
            df[target] = values
            if action.drop_sources:
                df = df.drop(columns=[name for name in columns if name != target])
            return df, f"{len(columns)} ta ustun '{target}' nomi bilan birlashtirildi"

    col = _column(df, action.column)
    blank = blank_mask(df[col])

    if kind == "drop_missing_rows":
        n = int(blank.sum())
        return df[~blank], f"'{col}' ustuni bo'sh bo'lgan {n} ta qator olib tashlandi"

    if kind == "fill_missing":
        n = int(blank.sum())
        if n == 0:
            return df, f"'{col}' ustunida bo'sh qiymat yo'q"

        method = action.method
        if method in ("median", "mean"):
            nums = pd.to_numeric(df.loc[~blank, col], errors="coerce").dropna()
            if nums.empty:
                raise CleanError(f"'{col}' ustuni raqamli emas, {method} hisoblab bo'lmaydi")
            stat = nums.median() if method == "median" else nums.mean()
            fill = str(int(stat)) if float(stat).is_integer() else f"{stat:.2f}"
        elif method == "mode":
            modes = df.loc[~blank, col].astype(str).str.strip().mode()
            if modes.empty:
                raise CleanError(f"'{col}' ustunida eng ko'p uchraydigan qiymat topilmadi")
            fill = str(modes.iloc[0])
        elif method == "value":
            if not action.value:
                raise CleanError("'value' usuli uchun 'value' maydoni kerak")
            fill = action.value
        else:
            raise CleanError("'method' kerak: median, mean, mode yoki value")

        df.loc[blank, col] = fill
        return df, f"'{col}' ustunidagi {n} ta bo'sh qiymat '{fill}' bilan to'ldirildi"

    if kind == "invalid_to_empty":
        values = df.loc[~blank, col].astype(str).str.strip()
        col_type = detect_type(values)
        if col_type == "number":
            bad = pd.to_numeric(values, errors="coerce").isna()
        elif col_type == "date":
            bad = pd.to_datetime(values, errors="coerce", format="mixed").isna()
        else:
            raise CleanError(f"'{col}' ustuni raqam yoki sana emas")
        bad_index = bad.index[bad.to_numpy()]
        df.loc[bad_index, col] = None
        return df, f"'{col}' ustunidagi {len(bad_index)} ta noto'g'ri qiymat bo'shatildi"

    raise CleanError(f"Noma'lum amal: {kind}")