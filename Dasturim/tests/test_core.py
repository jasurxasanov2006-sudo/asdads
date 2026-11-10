from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from ai import AIError, ask_question, check_sql, run_query_tables, set_runtime_settings, typed_frame
from cleaning import apply_action, near_duplicate_groups
from extras import guard as extras_guard
from profiling import detect_type, profile_dataframe
from pycells import guard as py_guard


def action(kind, **kwargs):
    defaults = {
        "columns": None,
        "column": None,
        "method": None,
        "value": None,
        "mode": None,
        "new_name": None,
        "second_column": None,
        "target_column": None,
        "separator": None,
        "drop_sources": False,
        "replacements": None,
        "decimal_separator": ".",
        "thousands_separator": None,
        "date_format": None,
    }
    return SimpleNamespace(type=kind, **(defaults | kwargs))


def test_profile_sample_finds_missing_duplicate_and_bad_values():
    path = Path(__file__).resolve().parents[1] / "test-data" / "sample.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)

    report = profile_dataframe(frame)
    issue_types = {issue["type"] for issue in report["issues"]}

    assert report["summary"]["rows"] == 5
    assert {"missing", "duplicate", "invalid_number", "invalid_date"} <= issue_types


def test_profile_detects_outlier_with_project_threshold():
    frame = pd.DataFrame({"value": [*range(30), 1000]})

    report = profile_dataframe(frame)

    outlier = next(issue for issue in report["issues"] if issue["type"] == "outlier")
    assert outlier["count"] == 1


def test_detect_type_handles_empty_number_date_and_text():
    assert detect_type(pd.Series([], dtype=str)) == "empty"
    assert detect_type(pd.Series(["1", "2", "3"])) == "number"
    assert detect_type(pd.Series(["2026-01-01", "2026-01-02"])) == "date"
    assert detect_type(pd.Series(["Ali", "Vali"])) == "text"


def test_large_column_type_sampling_preserves_majority_threshold():
    numeric = pd.Series(["1"] * 12000 + ["not-a-number"] * 8000)
    text = pd.Series(["description"] * 20000)

    assert detect_type(numeric) == "number"
    assert detect_type(text) == "text"


@pytest.mark.parametrize(
    ("kind", "frame", "kwargs", "expected"),
    [
        ("remove_duplicates", pd.DataFrame({"x": ["a", "a", "b"]}), {}, 2),
        ("trim_text", pd.DataFrame({"x": [" a ", "b  "]}), {}, ["a", "b"]),
        ("drop_missing_rows", pd.DataFrame({"x": ["", "a"]}), {"column": "x"}, 1),
        ("fill_missing", pd.DataFrame({"x": ["2", "", "4"]}), {"column": "x", "method": "median"}, "3"),
        ("fill_missing", pd.DataFrame({"x": ["2", "", "4"]}), {"column": "x", "method": "mean"}, "3"),
        ("fill_missing", pd.DataFrame({"x": ["a", "", "a"]}), {"column": "x", "method": "mode"}, "a"),
        ("fill_missing", pd.DataFrame({"x": ["a", ""]}), {"column": "x", "method": "value", "value": "noma'lum"}, "noma'lum"),
        ("invalid_to_empty", pd.DataFrame({"x": ["1", "2", "abc"]}), {"column": "x"}, None),
        ("invalid_to_empty", pd.DataFrame({"x": ["2026-01-01", "2026-01-02", "noto'g'ri"]}), {"column": "x"}, None),
    ],
)
def test_cleaning_actions(kind, frame, kwargs, expected):
    result, _ = apply_action(frame, action(kind, **kwargs))

    if kind == "remove_duplicates":
        assert len(result) == expected
    elif kind == "trim_text":
        assert result["x"].tolist() == expected
    elif kind == "drop_missing_rows":
        assert len(result) == expected
    elif kind == "fill_missing":
        assert result["x"].iloc[1] == expected
    elif kind == "invalid_to_empty":
        assert pd.isna(result["x"].iloc[-1])


def test_cleaning_rejects_missing_column():
    with pytest.raises(ValueError, match="Ustun topilmadi"):
        apply_action(pd.DataFrame({"x": ["a"]}), action("drop_missing_rows", column="y"))


@pytest.mark.parametrize(
    ("mode", "source", "expected"),
    [
        ("trim", "  Ali  ", "Ali"),
        ("lower", "Ali", "ali"),
        ("upper", "Ali", "ALI"),
        ("spaces", "A   B", "A B"),
    ],
)
def test_normalize_text(mode, source, expected):
    result, _ = apply_action(
        pd.DataFrame({"name": [source]}), action("normalize_text", column="name", mode=mode)
    )
    assert result["name"].iloc[0] == expected


def test_convert_number_with_thousands_and_decimal_separator():
    result, _ = apply_action(
        pd.DataFrame({"amount": ["1.234,50", "noto'g'ri", ""]}),
        action(
            "convert_number",
            column="amount",
            decimal_separator=",",
            thousands_separator=".",
        ),
    )
    assert result["amount"].iloc[0] == "1234.5"
    assert pd.isna(result["amount"].iloc[1])


def test_convert_date_and_format_to_iso():
    result, _ = apply_action(
        pd.DataFrame({"date": ["31/01/2026", "not-a-date"]}),
        action("convert_date", column="date", date_format="%d/%m/%Y"),
    )
    assert result["date"].iloc[0] == "2026-01-31"
    assert pd.isna(result["date"].iloc[1])


def test_date_to_iso_accepts_mixed_formats():
    result, _ = apply_action(
        pd.DataFrame({"date": ["2026-01-31", "31 Jan 2026"]}),
        action("date_to_iso", column="date"),
    )
    assert result["date"].tolist() == ["2026-01-31", "2026-01-31"]


def test_rename_and_drop_column():
    result, _ = apply_action(
        pd.DataFrame({"old": ["x"], "unused": ["y"]}),
        action("rename_column", column="old", new_name="new"),
    )
    result, _ = apply_action(result, action("drop_column", column="unused"))
    assert list(result.columns) == ["new"]


def test_split_and_merge_columns():
    frame = pd.DataFrame({"full": ["Ali Vali", "Bobur Karim"], "city": ["Toshkent", "Buxoro"]})
    split, _ = apply_action(
        frame,
        action("split_column", column="full", new_name="first", second_column="last", separator=" "),
    )
    assert split["first"].tolist() == ["Ali", "Bobur"]
    assert split["last"].tolist() == ["Vali", "Karim"]
    merged, _ = apply_action(
        split,
        action(
            "merge_columns",
            columns=["first", "city"],
            new_name="label",
            separator=", ",
            drop_sources=True,
        ),
    )
    assert merged["label"].tolist() == ["Ali, Toshkent", "Bobur, Buxoro"]
    assert "first" not in merged.columns


def test_replace_values_and_fill_missing_unknown():
    frame = pd.DataFrame({"city": ["Toshkent", "", "toshkent"]})
    replaced, _ = apply_action(
        frame,
        action("replace_values", column="city", replacements={"Toshkent": "Poytaxt"}),
    )
    filled, _ = apply_action(
        replaced, action("fill_missing_unknown", column="city", value="noma'lum")
    )
    assert filled["city"].tolist() == ["Poytaxt", "noma'lum", "toshkent"]


def test_near_duplicate_groups_normalize_case_and_spaces():
    frame = pd.DataFrame({"name": ["  Ali   Vali", "ali vali", "Bobur"]})

    groups = near_duplicate_groups(frame, ["name"])

    assert groups == [{"rows": [2, 3], "count": 2}]


def test_near_duplicate_group_limits_displayed_rows():
    frame = pd.DataFrame({"name": ["ali"] * 30})

    groups = near_duplicate_groups(frame, ["name"])

    assert groups[0]["count"] == 30
    assert len(groups[0]["rows"]) == 10


def test_remove_near_duplicates_keeps_first_matching_row():
    frame = pd.DataFrame({"name": ["  Ali   Vali", "ali vali", "Bobur"], "id": [1, 2, 3]})

    result, _ = apply_action(frame, action("remove_near_duplicates", columns=["name"]))

    assert result["id"].tolist() == [1, 3]


def test_cleaning_rejects_conflicting_or_ambiguous_options():
    with pytest.raises(ValueError, match="allaqachon bor"):
        apply_action(pd.DataFrame({"name": ["Ali"]}), action("rename_column", column="name", new_name="name"))
    with pytest.raises(ValueError, match="ajratgichlari har xil"):
        apply_action(
            pd.DataFrame({"n": ["1"]}),
            action("convert_number", column="n", decimal_separator=",", thousands_separator=","),
        )


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM data",
        "SELECT 1; DROP TABLE data",
        "SELECT * FROM read_csv('secret.csv')",
        "SELECT * FROM data; SELECT 1",
    ],
)
def test_check_sql_rejects_unsafe_queries(sql):
    with pytest.raises(AIError):
        check_sql(sql)


def test_check_sql_accepts_select_and_with():
    assert check_sql(" SELECT 1; ") == "SELECT 1"
    assert check_sql("WITH x AS (SELECT 1 AS n) SELECT n FROM x").startswith("WITH")


def test_typed_frame_converts_numeric_date_and_keeps_text():
    frame = pd.DataFrame(
        {"number": ["1", "2", ""], "date": ["2026-01-01", "2026-01-02", ""], "name": ["Ali", "", "Vali"]}
    )

    typed = typed_frame(frame)

    assert pd.api.types.is_numeric_dtype(typed["number"])
    assert pd.api.types.is_datetime64_any_dtype(typed["date"])
    assert typed["name"].iloc[1] is None or pd.isna(typed["name"].iloc[1])


def test_run_query_tables_returns_rows_and_columns():
    columns, rows, truncated = run_query_tables(
        {"people": pd.DataFrame({"name": ["Ali", "Vali"], "age": [25, 30]})},
        "SELECT name FROM people ORDER BY age",
    )

    assert columns == ["name"]
    assert rows == [["Ali"], ["Vali"]]
    assert truncated is False


def test_ai_question_honors_sample_privacy_setting(monkeypatch):
    import ai

    prompts = []

    def load_test_settings(path, override):
        monkeypatch.setenv("AI_SEND_SAMPLE", "false")

    def fake_model(system, user):
        prompts.append(user)
        return '{"sql":"SELECT COUNT(*) AS n FROM data","explanation":"Hisoblandi."}'

    monkeypatch.setattr(ai, "load_dotenv", load_test_settings)
    monkeypatch.setattr(ai, "call_model", fake_model)

    result = ai.ask_question(pd.DataFrame({"name": ["Ali"]}), "Nechta qator bor?")

    assert result["rows"] == [[1]]
    assert len(prompts) == 1
    assert "Namuna qatorlar" not in prompts[0]


def test_ai_question_uses_recent_history_context(monkeypatch):
    import ai

    prompts = []

    def fake_model(system, user):
        prompts.append(user)
        return '{"sql":"SELECT COUNT(*) AS n FROM data","explanation":"Hisoblandi."}'

    monkeypatch.setattr(ai, "call_model", fake_model)
    ai.AI_CONTEXT["abc"] = ["Qaysi davlatlar bor?", "Yoshlar nechta?"]

    ai.ask_question(pd.DataFrame({"name": ["Ali"]}), "Nechta qator bor?", file_id="abc")

    assert "Oldingi savollar:" in prompts[0]
    assert "Qaysi davlatlar bor?" in prompts[0]


def test_runtime_settings_store_provider_and_limits(monkeypatch):
    import ai

    monkeypatch.setattr(ai, "ENV_FILE", Path("C:/Users/Asus/Desktop/Dasturim/backend/.env"))
    settings = set_runtime_settings({"provider": "gemini", "send_sample": False, "history_limit": 3, "query_limit": 7})

    assert settings["provider"] == "gemini"
    assert settings["send_sample"] is False
    assert settings["history_limit"] == 3
    assert settings["query_limit"] == 7


def test_call_model_reports_quota_and_provider_messages(monkeypatch):
    import ai

    def boom(system, user):
        raise ai.AIError(ai._friendly_provider_error("Gemini", "429 Resource Exhausted"))

    monkeypatch.setattr(ai, "_call_model_once", boom)

    with pytest.raises(ai.AIError, match="Gemini.*kvota|kvota.*Gemini"):
        ai.call_model("system", "user")


def test_call_model_falls_back_to_other_provider(monkeypatch):
    import ai

    calls = []

    def fake_call_once(system, user, provider=None):
        calls.append(provider)
        if provider == "gemini":
            raise ai.AIError("429 Resource Exhausted")
        return '{"sql":"SELECT 1 AS ok","explanation":"OK"}'

    monkeypatch.setattr(ai, "_call_model_once", fake_call_once)
    monkeypatch.setattr(ai, "_provider_candidates", lambda preferred=None: ["gemini", "claude"])

    result = ai.call_model("system", "user")

    assert result == '{"sql":"SELECT 1 AS ok","explanation":"OK"}'
    assert calls == ["gemini", "claude"]


def request(host="127.0.0.1:8000", client="127.0.0.1", marker="1"):
    headers = [(b"host", host.encode()), (b"x-dataflow", marker.encode())]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/test",
            "raw_path": b"/test",
            "query_string": b"",
            "headers": headers,
            "client": (client, 1234),
            "server": ("127.0.0.1", 8000),
        }
    )


@pytest.mark.parametrize("guard", [py_guard, extras_guard])
def test_local_guards_accept_and_reject_requests(guard):
    guard(request())
    with pytest.raises(HTTPException) as error:
        guard(request(client="192.168.1.20"))
    assert error.value.status_code == 403

    with pytest.raises(HTTPException) as error:
        guard(request(marker=""))
    assert error.value.status_code == 403
