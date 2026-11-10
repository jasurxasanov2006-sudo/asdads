import json
import os
import re
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import duckdb
import pandas as pd
from dotenv import load_dotenv

from profiling import detect_type, profile_dataframe

ENV_FILE = Path(
    os.getenv("DATAFLOW_AI_ENV_FILE", str(Path(__file__).resolve().parent / ".env"))
).expanduser().resolve()
MAX_ROWS = 200

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|export|import|install|"
    r"load|pragma|call|set|truncate|glob|read_\w+|write_\w+)\b",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """Sen DuckDB SQL mutaxassisisan. Foydalanuvchi bitta yoki bir nechta jadval bo'yicha savol beradi.
Agar ko'p jadval berilgan bo'lsa, tegishli JOIN yozish mumkin; aksi holda bitta `data` jadvali ishlatiladi.
Qoidalar:
- Faqat bitta SELECT (yoki WITH ... SELECT) so'rovi yoz.
- Faqat berilgan ustunlardan foydalan. Ustun nomlarini "qo'sh tirnoq" ichida yoz.
- Bo'sh qiymatlar NULL bo'ladi.
- Jadval nomlarini ham to'g'ri yoz. Bir nechta jadval bo'lsa, JOIN kalitlarini mantiqiy moslashtirish kerak.
- Javobni FAQAT JSON qilib ber: {"sql": "...", "explanation": "..."}.
- "explanation": 1-2 gap, natija qanday hisoblangani. Savol qaysi tilda bo'lsa, shu tilda yoz.
- Savolga jadvaldagi ma'lumot bilan javob berib bo'lmasa: {"sql": "", "explanation": "sababi"}.
"""


class AIError(Exception):
    pass


class SandboxUnavailableError(AIError):
    pass


AI_CONTEXT: dict[str, list[str]] = {}
AI_QUERY_LOG: dict[str, int] = {}


def get_runtime_settings() -> dict:
    load_dotenv(ENV_FILE, override=True)
    gemini = os.getenv("GEMINI_API_KEY", "").strip()
    claude = os.getenv("ANTHROPIC_API_KEY", "").strip()
    pref = os.getenv("AI_PROVIDER", "").strip().lower()
    if pref not in {"gemini", "claude", "auto", ""}:
        pref = "auto"
    if pref == "auto":
        pref = "gemini" if gemini else "claude" if claude else "gemini"
    try:
        history_limit = max(0, int(os.getenv("AI_HISTORY_LIMIT", "5")))
    except ValueError:
        history_limit = 5
    try:
        query_limit = max(0, int(os.getenv("AI_QUERY_LIMIT", "10")))
    except ValueError:
        query_limit = 10
    send_sample = os.getenv("AI_SEND_SAMPLE", "true").strip().lower() != "false"
    provider_label = {"gemini": "Gemini", "claude": "Claude", "auto": "Avtomatik"}.get(pref, "Avtomatik")
    return {
        "provider": pref,
        "provider_label": provider_label,
        "send_sample": send_sample,
        "history_limit": history_limit,
        "query_limit": query_limit,
        "privacy_label": "Namuna qatorlar yuboriladi" if send_sample else "Namuna qatorlar yuborilmaydi",
    }


def set_runtime_settings(data: dict) -> dict:
    current = get_runtime_settings()
    provider = str(data.get("provider", current["provider"]) or current["provider"]).strip().lower()
    if provider not in {"gemini", "claude", "auto"}:
        provider = current["provider"]
    send_sample = bool(data.get("send_sample", current["send_sample"]))
    history_limit = max(0, int(data.get("history_limit", current["history_limit"])))
    query_limit = max(0, int(data.get("query_limit", current["query_limit"])))
    env_mapping = {
        "AI_PROVIDER": "" if provider == "auto" else provider,
        "AI_SEND_SAMPLE": "true" if send_sample else "false",
        "AI_HISTORY_LIMIT": str(history_limit),
        "AI_QUERY_LIMIT": str(query_limit),
    }
    lines = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    seen = {line.split("=", 1)[0] for line in lines if "=" in line}
    for key, value in env_mapping.items():
        if key in seen:
            lines = [line for line in lines if not line.startswith(f"{key}=")]
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    for key, value in env_mapping.items():
        os.environ[key] = value
    return get_runtime_settings()


def record_recent_question(file_id: str, question: str, limit: int | None = None) -> list[str]:
    if not file_id:
        return []
    text = (question or "").strip()
    if not text:
        return []
    settings = get_runtime_settings()
    cap = limit if limit is not None else settings["history_limit"]
    history = AI_CONTEXT.setdefault(file_id, [])
    history.append(text)
    if cap <= 0:
        AI_CONTEXT[file_id] = []
    else:
        AI_CONTEXT[file_id] = history[-cap:]
    return AI_CONTEXT[file_id]


def recent_questions(file_id: str, limit: int | None = None) -> list[str]:
    if not file_id:
        return []
    cap = limit if limit is not None else get_runtime_settings()["history_limit"]
    history = AI_CONTEXT.get(file_id, [])
    return history[-cap:] if cap > 0 else []


def check_query_budget(file_id: str) -> None:
    limit = get_runtime_settings()["query_limit"]
    if limit <= 0:
        return
    count = AI_QUERY_LOG.get(file_id, 0) + 1
    if count > limit:
        raise AIError(
            f"AI so'rovlar limitiga yetdingiz: {limit} ta. Bir muddat kutib, keyinroq qayta urinib ko'ring."
        )
    AI_QUERY_LOG[file_id] = count


def _provider_label(provider: str | None = None) -> str:
    name = (provider or get_provider()[0]).strip().lower()
    return {"gemini": "Gemini", "claude": "Claude"}.get(name, "AI provider")


def _friendly_provider_error(provider_name: str, message: str) -> str:
    text = (message or "").strip()
    lower = text.lower()
    if any(k in lower for k in ("429", "rate limit", "quota", "resource_exhausted", "resource exhausted", "too many requests")):
        return (
            f"{provider_name} kvota yoki tezlik cheklovi tufayli to'xtatildi. "
            "Bir-ikki daqiqa kutib, keyin qayta urinib ko'ring yoki boshqa providerni tanlang."
        )
    if any(k in lower for k in ("503", "unavailable", "overloaded", "temporarily unavailable")):
        return (
            f"{provider_name} vaqtincha ishlamayapti. "
            "Bir oz kutib, qayta urunib ko'ring."
        )
    if "api key" in lower or "kalit" in lower or "key not found" in lower:
        return (
            f"{provider_name} uchun kalit topilmadi. backend/.env faylida GEMINI_API_KEY yoki ANTHROPIC_API_KEY mavjudligini tekshiring."
        )
    return f"{provider_name} bilan bog'lanishda xatolik yuz berdi: {text[:220]}"


def _provider_candidates(preferred: str | None = None) -> list[str]:
    pref = (preferred or get_runtime_settings()["provider"] or "").strip().lower()
    if pref not in {"gemini", "claude", "auto", ""}:
        pref = "auto"
    names = []
    if pref in {"gemini", "claude"}:
        names.append(pref)
    for name in ("gemini", "claude"):
        if name not in names:
            names.append(name)
    return [name for name in names if os.getenv(f"{name.upper()}_API_KEY", "").strip()]


def get_provider(pref: str | None = None):
    settings = get_runtime_settings()
    candidates = _provider_candidates(pref or settings["provider"])
    for name in candidates:
        key = os.getenv(f"{name.upper()}_API_KEY", "").strip()
        if key:
            return name, key
    raise AIError(
        "AI kaliti topilmadi. backend/.env fayliga GEMINI_API_KEY yoki ANTHROPIC_API_KEY yozing"
    )


def _call_model_once(system: str, user: str, provider: str | None = None) -> str:
    provider, key = get_provider(provider)
    try:
        if provider == "gemini":
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=key)
            resp = client.models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    temperature=0,
                ),
            )
            return resp.text or ""

        import anthropic

        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
            max_tokens=1200,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    except ImportError:
        raise AIError(
            "AI kutubxonasi o'rnatilmagan: pip install google-genai (yoki anthropic)"
        )
    except Exception as e:
        detail = f"{type(e).__name__}: {str(e)[:300]}"
        raise AIError(_friendly_provider_error(_provider_label(provider), detail))


def typed_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        s = out[col]
        blank = s.isna() | s.fillna("").astype(str).str.strip().eq("")
        kind = detect_type(s[~blank].astype(str).str.strip())
        if kind == "number":
            out[col] = pd.to_numeric(s.where(~blank), errors="coerce")
        elif kind == "date":
            out[col] = pd.to_datetime(s.where(~blank), errors="coerce", format="mixed")
        else:
            out[col] = s.where(~blank)
    return out


def schema_text(typed: pd.DataFrame, send_sample: bool) -> str:
    lines = []
    for col in typed.columns:
        dtype = typed[col].dtype
        if pd.api.types.is_numeric_dtype(dtype):
            kind = "number"
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            kind = "date"
        else:
            kind = "text"
        lines.append(f'- "{str(col).replace(chr(34), chr(34) * 2)}" ({kind})')
    text = "\n".join(lines)
    if send_sample:
        head = typed.head(5).astype(object)
        rows = head.where(head.notna(), None).to_dict(orient="records")
        text += "\n\nNamuna qatorlar:\n" + json.dumps(rows, ensure_ascii=False, default=str)
    return text


def tables_schema_text(tables: dict[str, pd.DataFrame], send_sample: bool) -> str:
    blocks = []
    for name, frame in tables.items():
        typed = typed_frame(frame)
        blocks.append(f'Jadval "{name}":\n{schema_text(typed, send_sample)}')
    return "\n\n".join(blocks)


def parse_json_object(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise AIError("AI javobini o'qib bo'lmadi. Savolni boshqacha yozib ko'ring")
        try:
            data = json.loads(match.group(0))
        except ValueError:
            raise AIError("AI javobini o'qib bo'lmadi. Savolni boshqacha yozib ko'ring")
    if not isinstance(data, dict):
        raise AIError("AI javobini o'qib bo'lmadi. Savolni boshqacha yozib ko'ring")
    return data


def parse_reply(text: str):
    data = parse_json_object(text)
    return str(data.get("sql", "")).strip(), str(data.get("explanation", "")).strip()


def strip_quoted(sql: str) -> str:
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    return re.sub(r'"(?:[^"]|"")*"', '""', sql)


def check_sql(sql: str) -> str:
    sql = sql.strip().rstrip(";").strip()
    bare = strip_quoted(sql)
    if ";" in bare:
        raise AIError("Xavfsizlik: faqat bitta so'rovga ruxsat beriladi")
    if not re.match(r"^\s*(select|with)\b", bare, re.IGNORECASE):
        raise AIError("Xavfsizlik: faqat SELECT so'rovlariga ruxsat beriladi")
    if FORBIDDEN.search(bare):
        raise AIError("Xavfsizlik: so'rovda ruxsat etilmagan amal bor")
    return sql


def jsonable(v):
    if v is None:
        return None
    if isinstance(v, float):
        return None if v != v else round(v, 4)
    if isinstance(v, Decimal):
        return round(float(v), 4)
    if isinstance(v, (int, bool, str)):
        return v
    return str(v)


def run_query_tables(tables: dict, sql: str, limit: int = MAX_ROWS):
    if os.getenv("DATAFLOW_PYTHON_SANDBOX", "local").strip().lower() == "docker":
        endpoint = os.getenv("DATAFLOW_PYTHON_SANDBOX_URL", "").strip()
        sandbox_token = os.getenv("DATAFLOW_SANDBOX_TOKEN", "")
        if not endpoint or len(sandbox_token) < 32:
            raise SandboxUnavailableError("Izolyatsiyalangan SQL/Python sandbox sozlamasi to'liq emas")
        frames = {}
        for name, frame in tables.items():
            serialized = json.loads(frame.to_json(orient="split", date_format="iso", default_handler=str))
            frames[name] = {"columns": serialized["columns"], "rows": serialized["data"]}
        payload = json.dumps({
            "kind": "sql",
            "execution_id": uuid4().hex,
            "frames": frames,
            "sql": sql,
            "limit": max(1, min(int(limit), 1000)),
        }, ensure_ascii=False).encode("utf-8")
        if len(payload) > 256 * 1024 * 1024:
            raise SandboxUnavailableError("SQL sandbox uchun jadval ma'lumotlari 256 MB dan katta")
        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {sandbox_token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                result = json.loads(response.read(16 * 1024 * 1024 + 1))
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read(4096)).get("detail", "SQL sandbox xatosi")
            except (ValueError, AttributeError):
                detail = "SQL sandbox xatosi"
            raise SandboxUnavailableError(detail) from error
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            raise SandboxUnavailableError(
                f"SQL sandbox bilan bog'lanib bo'lmadi: {str(error)[:200]}"
            ) from error
        if isinstance(result, dict) and isinstance(result.get("error"), str):
            raise duckdb.Error(f"SQL xatosi: {result['error'][:400]}")
        if not isinstance(result, dict) or not {"columns", "rows", "truncated"} <= result.keys():
            raise SandboxUnavailableError("SQL sandbox javobining formati noto'g'ri")
        return result["columns"], result["rows"], result["truncated"]

    con = duckdb.connect(":memory:")
    try:
        for i, (name, frame) in enumerate(tables.items()):
            view = f"_v{i}"
            con.register(view, frame)
            safe = name.replace('"', '""')
            con.execute(f'CREATE TABLE "{safe}" AS SELECT * FROM {view}')
            con.unregister(view)
        con.execute("SET enable_external_access=false")  # fayllarga kirishni yopish
        con.execute("SET lock_configuration=true")
        cur = con.execute(sql)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(limit + 1)
    finally:
        con.close()
    truncated = len(rows) > limit
    rows = [[jsonable(v) for v in r] for r in rows[:limit]]
    return columns, rows, truncated


def run_query(typed: pd.DataFrame, sql: str, limit: int = MAX_ROWS):
    return run_query_tables({"data": typed}, sql, limit)


EXPLAIN_SQL_PROMPT = """Sen SQL ustozisan. Foydalanuvchi SQL so'rovini va jadval sxemasini beradi.
Qoidalar:
- O'zbek tilida qadam-baqadam tushuntir.
- 4-6 qadam bo'lsin, oddiy va aniq.
- Agar SQL xato bo'lsa, xato sababini aytib, to'g'ri SQL variantini ham ko'rsating.
- Faqat JSON qo'yib ber: {"explanation": "...", "fixed_sql": "..."}
"""

EXPLAIN_PY_PROMPT = """Sen Python va pandas ustozisan. Foydalanuvchi Python kodini beradi.
Qoidalar:
- O'zbek tilida qadam-baqadam tushuntir.
- Xatolik bo'lsa, nima sabab bo'lganini va tuzatilgan kodni ko'rsating.
- Faqat JSON: {"explanation": "...", "fixed_code": "..."}
"""


def explain_sql(sql: str, tables: dict[str, pd.DataFrame] | None = None, error: str | None = None) -> dict:
    sql = (sql or "").strip()
    if not sql:
        raise AIError("SQL bo'sh")
    table_map = {name: typed_frame(frame) for name, frame in (tables or {}).items()}
    if not table_map:
        raise AIError("SQLni tushuntirish uchun jadval sxemasi kerak")
    prompt = f"Jadval sxemasi:\n{tables_schema_text(table_map, send_sample=False)}\n\nSQL:\n{sql}\n\nXato: {error or 'Yo\'q'}"
    data = parse_json_object(call_model(EXPLAIN_SQL_PROMPT, prompt))
    fixed_sql = str(data.get("fixed_sql") or data.get("sql") or sql).strip()
    explanation = str(data.get("explanation") or "SQL qadam-baqadam tushuntirildi.").strip()
    return {"sql": fixed_sql, "explanation": explanation}


def explain_python(code: str, error: str | None = None) -> dict:
    code = (code or "").strip()
    if not code:
        raise AIError("Kod bo'sh")
    prompt = f"Python kodi:\n{code}\n\nXato: {error or 'Yo\'q'}"
    data = parse_json_object(call_model(EXPLAIN_PY_PROMPT, prompt))
    fixed_code = str(data.get("fixed_code") or data.get("code") or code).strip()
    explanation = str(data.get("explanation") or "Kod qadam-baqadam tushuntirildi.").strip()
    return {"code": fixed_code, "explanation": explanation}


CLEANING_HELPER_PROMPT = """Sen ma'lumotlarni tozalash bo'yicha mutaxassis san.
Foydalanuvchi ma'lumotlar profili va namuna qatorlarni beradi.
Qoidalar:
- O'zbek tilida 1-5 ta xavfsiz va foydali tozalash qadami ayt.
- Har bir qadam `type`, `column`, `reason` maydonlariga ega bo'lsin.
- `type` uchun faqat quyidagilarni ishlat: trim_text, normalize_text, fill_missing_unknown, convert_number, convert_date, drop_column, remove_duplicates, replace_values.
- Faqat JSON: {"steps": [{...}]}
"""

INSIGHT_PROMPT = """Sen ma'lumotlar analitikasan. Faqat FARAZ ko'rinishida kuzatuvlar toping.
Qoidalar:
- Har bir kuzatuvga `label`, `type`, `title`, `description`, `sql` bo'lsin.
- `label` doim "FARAZ" bo'lsin.
- `type` faqat "trend", "anomaly" yoki "segment" bo'lsin.
- Har bir fikr aniq haqiqat deb aytilmasin; "bunga o'xshash bo'lishi mumkin" yoki "FARAZ" tarzida izoh ber.
- `sql` mustaqil SELECT/WITH ... SELECT bo'lsin, ma'lumotni tekshirish uchun ishlatiladi.
- Faqat JSON: {"insights": [{...}]}
"""


def _fallback_insights(df: pd.DataFrame, limit: int = 3) -> list[dict]:
    if df.empty:
        return []
    columns = list(df.columns)
    numeric = [c for c in columns if pd.api.types.is_numeric_dtype(df[c])]
    text = [c for c in columns if not pd.api.types.is_numeric_dtype(df[c])]
    insights = []

    if numeric:
        col = numeric[0]
        avg = pd.to_numeric(df[col], errors="coerce").dropna().mean()
        sql = f'SELECT COUNT(*) AS above_avg_rows, AVG("{col}") AS avg_value FROM data WHERE "{col}" > {avg if pd.notna(avg) else 0}'
        insights.append({
            "label": "FARAZ",
            "type": "trend",
            "title": f"{col} ustunida yuqori qiymatlar kuzatilishi mumkin",
            "description": f"FARAZ: {col} o'rtacha qiymatdan yuqori qatorlar mavjud bo'lishi mumkin; bu trendni tekshirish kerak.",
            "sql": check_sql(sql),
        })

    if text:
        col = text[0]
        sql = f'SELECT "{col}", COUNT(*) AS cnt FROM data GROUP BY "{col}" ORDER BY cnt DESC LIMIT 5'
        insights.append({
            "label": "FARAZ",
            "type": "segment",
            "title": f"{col} bo'yicha segmentlar ajralishi mumkin",
            "description": f"FARAZ: {col} ustunidagi guruhlar orasida dominant segmentlar mavjud bo'lishi mumkin; bu guruhlarni tekshirish lozim.",
            "sql": check_sql(sql),
        })

    if len(insights) < limit:
        col = numeric[1] if len(numeric) > 1 else (text[0] if text else columns[0])
        if pd.api.types.is_numeric_dtype(df[col]):
            q = pd.to_numeric(df[col], errors="coerce").dropna()
            if not q.empty:
                low = q.quantile(0.1)
                high = q.quantile(0.9)
                sql = f'SELECT COUNT(*) AS outlier_like_rows FROM data WHERE "{col}" < {low} OR "{col}" > {high}'
                insights.append({
                    "label": "FARAZ",
                    "type": "anomaly",
                    "title": f"{col} ustunida anomaliya ko'rinishi mumkin",
                    "description": f"FARAZ: {col} qiymatlari past yoki yuqori qismga surilishi mumkin; bu chetga chiqqan holatlarni tekshirish kerak.",
                    "sql": check_sql(sql),
                })

    return insights[:limit]


def suggest_cleaning_steps(df: pd.DataFrame, limit: int = 5) -> dict:
    if df.empty:
        return {"steps": []}
    profile = profile_dataframe(df)
    sample = df.head(5).astype(object).where(df.head(5).notna(), None).to_dict(orient="records")
    prompt = (
        f"Jadval profili:\n{json.dumps(profile, ensure_ascii=False, default=str)}\n\n"
        f"Namuna qatorlar:\n{json.dumps(sample, ensure_ascii=False, default=str)}\n\n"
        "Qaysi tozalash qadamlari foydali bo'ladi?"
    )
    data = parse_json_object(call_model(CLEANING_HELPER_PROMPT, prompt))
    steps = data.get("steps", [])
    if not isinstance(steps, list):
        raise AIError("AI tozalash tavsiyalarini o'qib bo'lmadi")
    valid = []
    allowed = {
        "trim_text",
        "normalize_text",
        "fill_missing_unknown",
        "convert_number",
        "convert_date",
        "drop_column",
        "remove_duplicates",
        "replace_values",
    }
    for item in steps[:limit]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type", "")).strip()
        if kind not in allowed:
            continue
        valid.append({
            "type": kind,
            "column": item.get("column"),
            "reason": str(item.get("reason") or "Tozalash kerak.").strip(),
        })
    return {"steps": valid}


def generate_insights(df: pd.DataFrame, tables: dict[str, pd.DataFrame] | None = None, limit: int = 3) -> list[dict]:
    if df is None or df.empty:
        return []
    table_map = {name: frame for name, frame in (tables or {}).items()} if tables else {"data": df}
    if not table_map:
        table_map = {"data": df}
    profile = profile_dataframe(df)
    sample = df.head(5).astype(object).where(df.head(5).notna(), None).to_dict(orient="records")
    prompt = (
        f"Jadval profili:\n{json.dumps(profile, ensure_ascii=False, default=str)}\n\n"
        f"Namuna qatorlar:\n{json.dumps(sample, ensure_ascii=False, default=str)}\n\n"
        "Ma'lumotdan trend, anomaliya va segment bo'yicha FARAZ kuzatuvlar toping."
    )
    try:
        data = parse_json_object(call_model(INSIGHT_PROMPT, prompt))
        insights = data.get("insights", [])
    except AIError:
        return _fallback_insights(df, limit=limit)
    if not isinstance(insights, list):
        return _fallback_insights(df, limit=limit)
    valid = []
    for item in insights[:limit]:
        if not isinstance(item, dict):
            continue
        sql = str(item.get("sql") or "").strip()
        if not sql:
            continue
        try:
            clean_sql = check_sql(sql)
        except AIError:
            continue
        kind = str(item.get("type") or "trend").strip().lower()
        if kind not in {"trend", "anomaly", "segment"}:
            kind = "trend"
        valid.append({
            "label": str(item.get("label") or "FARAZ").strip() or "FARAZ",
            "type": kind,
            "title": str(item.get("title") or f"{kind.title()} FARAZ").strip(),
            "description": str(item.get("description") or "Bu kuzatuvni tekshirish kerak.").strip(),
            "sql": clean_sql,
        })
    return valid[:limit] if valid else _fallback_insights(df, limit=limit)


def ask_question(
    df: pd.DataFrame,
    question: str,
    tables: dict[str, pd.DataFrame] | None = None,
    file_id: str | None = None,
    history: list[str] | None = None,
) -> dict:
    load_dotenv(ENV_FILE, override=True)
    question = question.strip()
    if not question:
        raise AIError("Savol bo'sh")
    if len(question) > 500:
        raise AIError("Savol juda uzun (500 belgigacha)")

    if tables is None:
        tables = {"data": typed_frame(df)}
    else:
        tables = {name: typed_frame(frame) for name, frame in tables.items()}
        tables.setdefault("data", typed_frame(df))

    send_sample = get_runtime_settings()["send_sample"]
    context_lines = []
    if history is not None:
        visible_history = list(history)
    else:
        visible_history = recent_questions(file_id or "")
    if visible_history:
        context_lines.append("Oldingi savollar:\n" + "\n".join(f"- {item}" for item in visible_history[-5:]))
    user = f"{tables_schema_text(tables, send_sample)}\n\n" + ("\n\n".join(context_lines) + "\n\n" if context_lines else "") + f"Savol: {question}"

    last_error, bad_sql = None, ""
    for _ in range(2):  # xato chiqsa, AI'ga bir marta qayta urinish beramiz
        prompt = user
        if last_error:
            prompt += f"\n\nOldingi SQL xato berdi.\nSQL: {bad_sql}\nXato: {last_error}\nTuzatilgan SQL yoz."
        sql, explanation = parse_reply(call_model(SYSTEM_PROMPT, prompt))
        if not sql:
            return {
                "sql": "",
                "explanation": explanation or "Bu savolga javob topilmadi",
                "columns": [],
                "rows": [],
                "truncated": False,
            }
        sql = check_sql(sql)
        try:
            columns, rows, truncated = run_query_tables(tables, sql)
        except duckdb.Error as e:
            last_error, bad_sql = str(e)[:300], sql
            continue
        return {
            "sql": sql,
            "explanation": explanation,
            "columns": columns,
            "rows": rows,
            "truncated": truncated,
        }
    raise AIError(f"AI yozgan SQL ishlamadi: {last_error}")

import time as _time


def call_model(system: str, user: str) -> str:
    """AI band bo'lsa (503/429), 3 martagacha qayta urinadi. Agar kerak bo'lsa, boshqa providerni sinab ko'radi."""
    last = None
    providers = _provider_candidates()
    if not providers:
        get_provider()
    for attempt in range(3):
        retry_needed = False
        for provider in providers:
            try:
                try:
                    return _call_model_once(system, user, provider=provider)
                except TypeError as e:
                    if "provider" not in str(e):
                        raise
                    return _call_model_once(system, user)
            except AIError as e:
                last = e
                msg = str(e).lower()
                if not any(k in msg for k in ("503", "429", "unavailable", "resource_exhausted", "overloaded", "kvota", "tezlik", "quota", "rate limit")):
                    raise
                retry_needed = True
        if not retry_needed:
            break
        _time.sleep(3 * (attempt + 1))
    raise AIError(f"{last} (3 marta urinildi, birozdan keyin qayta urining)")
