import base64
import html
import io
import json
import logging
import re
import threading
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, time as datetime_time
from contextlib import nullcontext
from pathlib import Path
from typing import Callable, Literal
from uuid import uuid4

import duckdb
import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.drawing.image import Image as ExcelImage
from PIL import Image as PILImage
from pydantic import BaseModel

from ai import AIError, SandboxUnavailableError, check_sql, run_query_tables, typed_frame
from profiling import profile_dataframe
from report_templates import TEMPLATES, template_result
from stats import describe_dataframe

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
JS_FILE = ROOT / "frontend" / "extras.js"
BACKUPS = ROOT / "backups"
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
MAX_DOWNLOAD = 20 * 1024 * 1024
MAX_DB_ROWS = 200000
SKIP_DIRS = {"venv", "__pycache__", "backups", ".git", "node_modules"}
TYPE_LABELS = {"number": "raqam", "date": "sana", "text": "matn"}
SEV_LABELS = {"error": "Xato", "warning": "Ogohlantirish", "info": "Ma'lumot"}
REPORT_DEFAULTS = {
    "title": "DataFlow AI hisoboti",
    "logo": "",
    "schedule_enabled": False,
    "schedule_time": "02:00",
    "auto_save": False,
    "last_run": None,
    "last_error": "",
}
SCHEDULER_POLL_SECONDS = 20
LOG = logging.getLogger(__name__)


class OutIn(BaseModel):
    column: str
    k: float = 3.0
    action: Literal["preview", "clip", "remove"] = "preview"


class UrlIn(BaseModel):
    url: str


class DbIn(BaseModel):
    kind: Literal["postgres", "mysql"]
    host: str
    port: int | None = None
    user: str
    password: str = ""
    database: str
    query: str


class ReportSettingsIn(BaseModel):
    title: str = "DataFlow AI hisoboti"
    logo: str = ""
    schedule_enabled: bool = False
    schedule_time: str = "02:00"
    auto_save: bool = False


class TemplateRunIn(BaseModel):
    file_id: str
    columns: dict[str, str]


def guard(request: Request) -> None:
    """Yozuvchi amallar faqat shu kompyuterning o'z sahifasidan qabul qilinadi."""
    client = request.client.host if request.client else ""
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
    if client not in LOCAL_HOSTS or host not in LOCAL_HOSTS:
        raise HTTPException(403, "Bu amal faqat shu kompyuterning o'zida (127.0.0.1) ishlaydi")
    origin = request.headers.get("origin")
    if origin:
        oh = origin.split("://", 1)[-1].rsplit(":", 1)[0].strip("[]")
        if oh not in LOCAL_HOSTS:
            raise HTTPException(403, "So'rov manbai ruxsat etilmagan")
    if request.headers.get("x-dataflow") != "1":
        raise HTTPException(403, "So'rov manbai noto'g'ri")


def ints(n) -> str:
    return f"{int(n):,}".replace(",", " ")


def fmt(v) -> str:
    if v is None:
        return "-"
    try:
        s = f"{float(v):,.2f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(v)
    return s.rstrip("0").rstrip(".") if "." in s else s


def num_str(v: float) -> str:
    v = float(v)
    if v.is_integer():
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def spark(h, w: int = 10, hgt: int = 30) -> str:
    if not h or not h.get("counts"):
        return ""
    m = max(h["counts"]) or 1
    bars = ""
    for i, c in enumerate(h["counts"]):
        bh = max(1, round(c / m * hgt))
        bars += f'<rect x="{i * (w + 1)}" y="{hgt - bh}" width="{w}" height="{bh}" rx="2" fill="#4f6bed"/>'
    return f'<svg width="{len(h["counts"]) * (w + 1)}" height="{hgt}">{bars}</svg>'


def disposition(name: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", name) or "fayl"
    return f"attachment; filename=\"{safe}\"; filename*=UTF-8''{urllib.parse.quote(name)}"


REPORT_CSS = """
body{font-family:'Segoe UI',Arial,sans-serif;background:#f3f5fb;color:#0f172a;margin:0;padding:24px;font-size:14px}
.wrap{max-width:1000px;margin:0 auto}
h1{font-size:24px;margin:0 0 4px}
h2{font-size:17px;margin:0 0 12px}
h3{font-size:14px;margin:16px 0 6px}
.sub{color:#64748b;margin:0 0 20px}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:18px;margin-bottom:16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.kpis div{border:1px solid #e2e8f0;border-radius:12px;padding:12px 14px}
.kpis b{font-size:22px;display:block}
.kpis span{color:#64748b}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border-bottom:1px solid #e2e8f0;padding:7px 10px;text-align:left}
th{color:#64748b}
.scroll{overflow-x:auto}
.issue{border:1px solid #e2e8f0;border-left:4px solid #0891b2;border-radius:10px;padding:10px 14px;margin-bottom:10px}
.issue.error{border-left-color:#e11d48}
.issue.warning{border-left-color:#d97706}
.issue small{display:block;color:#64748b;margin-top:4px}
.hb{display:flex;align-items:center;gap:10px;margin:4px 0}
.hl{width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hbar{flex:1;background:#eef2ff;border-radius:6px;height:14px}
.hbar i{display:block;height:14px;border-radius:6px;background:linear-gradient(90deg,#4f6bed,#7c5cff)}
.hv{width:130px;text-align:right;color:#64748b}
ol,ul{margin:0;padding-left:20px;color:#475569}
.note{color:#64748b;font-size:12px}
@media print{body{background:#fff;padding:0}.card{break-inside:avoid;box-shadow:none}}
"""


def build_report(item: dict, settings: dict | None = None) -> str:
    e = html.escape
    settings = settings or REPORT_DEFAULTS
    versions = item["versions"]
    df = versions[-1]["df"]
    prof = profile_dataframe(df)
    st = describe_dataframe(df)
    summary = prof["summary"]
    total = st["rows"] or 1

    def table(head, rows, raw_columns=()):
        th = "".join(f"<th>{e(str(h))}</th>" for h in head)
        body = "".join(
            "<tr>" + "".join(
                f"<td>{c if index in raw_columns else e(str(c))}</td>"
                for index, c in enumerate(row)
            ) + "</tr>"
            for row in rows
        )
        return f"<div class='scroll'><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    out = [
        (
            f"<div class='report-brand'><img alt='Logotip' src='{e(settings['logo'])}'>"
            if settings.get("logo") else ""
        )
        + f"<h1>{e(settings.get('title') or 'DataFlow AI hisoboti')}</h1>"
        + f"<p class='sub'>{e(item['filename'])}</p>",
        f"<p class='sub'>Jadval: {e(item['table'])} · hisobot vaqti: {now} · DataFlow AI</p>",
        "<div class='card'><div class='kpis'>"
        f"<div><b>{ints(summary['rows'])}</b><span>qator</span></div>"
        f"<div><b>{summary['columns']}</b><span>ustun</span></div>"
        f"<div><b>{summary['issues']}</b><span>topilgan muammo</span></div>"
        f"<div><b>{len(versions) - 1}</b><span>tozalash qadami</span></div></div></div>",
    ]

    hist = "".join(f"<li>{e(v['label'])} <span class='note'>({ints(len(v['df']))} qator)</span></li>" for v in versions)
    out.append(f"<div class='card'><h2>O'zgarishlar tarixi</h2><ol>{hist}</ol></div>")

    if prof["issues"]:
        items = ""
        for i in prof["issues"]:
            rows = ", ".join(str(r) for r in i["rows"]) + (" ..." if i["count"] > len(i["rows"]) else "")
            ex = (" · Misollar: " + ", ".join(e(str(x)) for x in i["examples"])) if i["examples"] else ""
            items += (
                f"<div class='issue {e(i['severity'])}'><b>{e(SEV_LABELS.get(i['severity'], i['severity']))}:</b> "
                f"{e(i['message'])}<small>Qatorlar (faylda): {e(rows)}{ex}<br>Tavsiya: {e(i['suggestion'])}</small></div>"
            )
        out.append(f"<div class='card'><h2>Topilgan muammolar</h2>{items}</div>")
    else:
        out.append("<div class='card'><h2>Topilgan muammolar</h2><p>Muammo topilmadi.</p></div>")

    cols = st["columns"]
    out.append(
        "<div class='card'><h2>Ustunlar</h2>"
        + table(
            ["Ustun", "Turi", "Bo'sh", "Noyob"],
            [[c["name"], TYPE_LABELS.get(c["type"], c["type"]), f"{ints(c['missing'])} ({fmt(c['missing_pct'])}%)", str(c.get("unique", "-"))] for c in cols],
        )
        + "</div>"
    )

    nums = [c for c in cols if c["type"] == "number" and c.get("count")]
    if nums:
        out.append(
            "<div class='card'><h2>Raqamli ustunlar statistikasi</h2>"
            + table(
                ["Ustun", "O'rtacha", "Median", "Std", "Min", "Max", "Taqsimot"],
                [[c["name"], fmt(c["mean"]), fmt(c["median"]), fmt(c["std"]), fmt(c["min"]), fmt(c["max"]), spark(c.get("histogram"))] for c in nums],
                raw_columns={6},
            )
            + "</div>"
        )

    blocks = []
    for c in cols:
        if c["type"] == "text" and c.get("top"):
            mx = max(t["count"] for t in c["top"]) or 1
            bars = ""
            for t in c["top"]:
                bars += (
                    f"<div class='hb'><span class='hl'>{e(t['value'])}</span>"
                    f"<span class='hbar'><i style='width:{t['count'] * 100 / mx:.1f}%'></i></span>"
                    f"<span class='hv'>{ints(t['count'])} ({t['count'] * 100 / total:.1f}%)</span></div>"
                )
            blocks.append(f"<h3>{e(c['name'])} <span class='note'>noyob qiymatlar: {ints(c.get('unique', 0))}</span></h3>{bars}")
    if blocks:
        out.append("<div class='card'><h2>Matnli ustunlar: eng ko'p uchraydiganlar</h2>" + "".join(blocks) + "</div>")

    if st["correlations"]:
        li = "".join(
            f"<li>{e(x['a'])} va {e(x['b'])}: r = {x['r']} ({'to`g`ri' if x['r'] > 0 else 'teskari'})</li>"
            for x in st["correlations"]
        )
        out.append(
            f"<div class='card'><h2>Ustunlar orasidagi bog'liqlik</h2><ul>{li}</ul>"
            "<p class='note'>Bog'liqlik sababni isbotlamaydi: bu faqat birga o'zgarishni ko'rsatadi.</p></div>"
        )

    return (
        "<!DOCTYPE html><html lang='uz'><head><meta charset='utf-8'>"
        f"<title>{e(settings.get('title') or 'DataFlow AI hisoboti')}: {e(item['filename'])}</title>"
        f"<style>{REPORT_CSS}.report-brand{{display:flex;align-items:center;gap:12px}}"
        ".report-brand img{max-width:180px;max-height:70px;object-fit:contain}"
        ".print-action{position:fixed;right:24px;top:18px}"
        "@media print{.print-action{display:none}}</style></head>"
        f"<body><button class='print-action' onclick='window.print()'>PDF chop etish</button>"
        f"<div class='wrap'>{''.join(out)}</div>"
        "<script>if(new URLSearchParams(location.search).has('print'))"
        "addEventListener('load',()=>setTimeout(()=>window.print(),300));</script></body></html>"
    )


def _excel_value(value):
    if value is None:
        return None
    try:
        missing = pd.isna(value)
        if isinstance(missing, bool) and missing:
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, str):
        candidate = value.lstrip(" \t\r\n")
        if candidate.startswith(("=", "+", "-", "@")):
            try:
                float(candidate)
            except ValueError:
                value = "'" + value
        return value[:32767]
    if isinstance(value, (int, float, bool, datetime)):
        if isinstance(value, float) and not pd.notna(value):
            return None
        return value
    return str(value)[:32767]


def build_xlsx(item: dict, settings: dict | None = None) -> bytes:
    settings = settings or REPORT_DEFAULTS
    df = typed_frame(item["versions"][-1]["df"])
    profile = profile_dataframe(item["versions"][-1]["df"])
    stats = describe_dataframe(item["versions"][-1]["df"])
    workbook = Workbook(write_only=True)

    data_sheet = workbook.create_sheet("Ma'lumot")
    data_sheet.append([_excel_value(str(column)) for column in df.columns])
    for row in df.itertuples(index=False, name=None):
        data_sheet.append([_excel_value(value) for value in row])

    summary_sheet = workbook.create_sheet("Umumiy")
    summary_sheet.append([_excel_value(settings.get("title") or "DataFlow AI hisoboti")])
    summary_sheet.append(["Fayl", _excel_value(item["filename"])])
    summary_sheet.append(["Jadval", _excel_value(item["table"])])
    summary_sheet.append(["Hisobot vaqti", datetime.now().strftime("%Y-%m-%d %H:%M")])
    summary_sheet.append(["Qatorlar", profile["summary"]["rows"]])
    summary_sheet.append(["Ustunlar", profile["summary"]["columns"]])
    summary_sheet.append(["Muammolar", profile["summary"]["issues"]])
    summary_sheet.append(["Eslatma", "Natijalarni tekshiring; hisobot audit o'rnini bosmaydi."])
    if settings.get("logo"):
        encoded = settings["logo"].split(",", 1)[1]
        source = PILImage.open(io.BytesIO(base64.b64decode(encoded))).convert("RGBA")
        png = io.BytesIO()
        source.save(png, format="PNG")
        png.seek(0)
        logo = ExcelImage(png)
        scale = min(180 / logo.width, 72 / logo.height, 1)
        logo.width = int(logo.width * scale)
        logo.height = int(logo.height * scale)
        summary_sheet.add_image(logo, "D1")

    stats_sheet = workbook.create_sheet("Statistika")
    stats_sheet.append(["Ustun", "Turi", "Bo'sh", "Noyob", "O'rtacha", "Median", "Min", "Max", "Std"])
    for column in stats["columns"]:
        stats_sheet.append([_excel_value(value) for value in [
            column["name"],
            TYPE_LABELS.get(column["type"], column["type"]),
            column.get("missing", 0),
            column.get("unique"),
            column.get("mean"),
            column.get("median"),
            column.get("min"),
            column.get("max"),
            column.get("std"),
        ]])

    issue_sheet = workbook.create_sheet("Muammolar")
    issue_sheet.append(["Daraja", "Turi", "Ustun", "Soni", "Qatorlar", "Misollar", "Tavsiya"])
    for issue in profile["issues"]:
        issue_sheet.append([_excel_value(value) for value in [
            SEV_LABELS.get(issue["severity"], issue["severity"]),
            issue["type"],
            issue.get("column") or "",
            issue["count"],
            ", ".join(str(row) for row in issue["rows"]),
            ", ".join(str(value) for value in issue["examples"]),
            issue["suggestion"],
        ]])
    if not profile["issues"]:
        issue_sheet.append(["Muammo topilmadi"])

    charts_sheet = workbook.create_sheet("Grafiklar")
    numeric_rows = [
        row_index
        for row_index, column in enumerate(stats["columns"], start=2)
        if column["type"] == "number" and column.get("mean") is not None
    ]
    if numeric_rows:
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = "Raqamli ustunlar: o'rtacha va median"
        chart.y_axis.title = "Ustun"
        chart.x_axis.title = "Qiymat"
        chart.add_data(
            Reference(stats_sheet, min_col=5, max_col=6, min_row=1, max_row=max(numeric_rows)),
            titles_from_data=True,
        )
        chart.set_categories(Reference(stats_sheet, min_col=1, min_row=2, max_row=max(numeric_rows)))
        charts_sheet.add_chart(chart, "A1")
    else:
        charts_sheet.append(["Grafik chizish uchun raqamli ustun topilmadi."])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def safe_stem(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", Path(value).stem).strip("._") or "hisobot"


def make_router(
    files: dict,
    workspace: Path,
    save_version,
    save_meta,
    make_table_name,
    project_dir: Callable[[], Path] | None = None,
    workspace_context: Callable[[str], object] | None = None,
    workspace_users: Callable[[], list[str]] | None = None,
) -> APIRouter:
    router = APIRouter()

    def get_item(file_id: str) -> dict:
        item = files.get(file_id)
        if item is None:
            raise HTTPException(404, "Jadval topilmadi. Uni qayta yuklang")
        return item

    def report_settings_path() -> Path:
        root = project_dir() if project_dir else workspace
        folder = root / "reports"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "settings.json"

    def read_report_settings() -> dict:
        path = report_settings_path()
        if not path.is_file():
            return dict(REPORT_DEFAULTS)
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise HTTPException(500, f"Hisobot sozlamalarini o'qib bo'lmadi: {error}") from error
        return {**REPORT_DEFAULTS, **stored}

    def write_report_settings(settings: dict) -> None:
        path = report_settings_path()
        path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def saved_reports_dir() -> Path:
        root = project_dir() if project_dir else workspace
        folder = root / "reports" / "saved"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def refresh_reports(settings: dict, force_save: bool = False) -> None:
        reports = saved_reports_dir()
        for file_id, item in list(files.items()):
            stem = f"{safe_stem(item['filename'])}_{file_id[:8]}"
            html_report = build_report(item, settings)
            excel_report = build_xlsx(item, settings)
            if settings.get("auto_save") or force_save:
                (reports / f"{stem}.html").write_text(html_report, encoding="utf-8")
                (reports / f"{stem}.xlsx").write_bytes(excel_report)
        settings["last_run"] = datetime.now().isoformat(timespec="seconds")
        settings["last_error"] = ""
        write_report_settings(settings)

    scheduler_stop = threading.Event()
    scheduler_thread = None

    def scheduler_loop() -> None:
        last_attempt: dict[str, str] = {}
        while not scheduler_stop.wait(SCHEDULER_POLL_SECONDS):
            user_ids = workspace_users() if workspace_users else []
            targets = (
                [(user_id, workspace_context(user_id)) for user_id in user_ids]
                if workspace_context and user_ids else [(None, nullcontext())]
            )
            for user_id, context in targets:
                try:
                    with context:
                        try:
                            settings = read_report_settings()
                            today = datetime.now().date().isoformat()
                            try:
                                scheduled = datetime_time.fromisoformat(settings.get("schedule_time", "02:00"))
                            except ValueError:
                                LOG.error("Hisobot jadvali vaqti noto'g'ri: %s", settings.get("schedule_time"))
                                continue
                            schedule_key = str(report_settings_path())
                            if (
                                settings.get("schedule_enabled")
                                and datetime.now().time() >= scheduled
                                and last_attempt.get(schedule_key) != today
                                and files
                            ):
                                last_attempt[schedule_key] = today
                                refresh_reports(settings)
                        except Exception as error:
                            LOG.exception(
                                "Rejalashtirilgan hisobotni yangilash bajarilmadi (foydalanuvchi %s)",
                                user_id or "local",
                            )
                            try:
                                settings = read_report_settings()
                                settings["last_error"] = f"{type(error).__name__}: {str(error)[:300]}"
                                write_report_settings(settings)
                            except Exception:
                                LOG.exception("Hisobot xatosini sozlamalarda saqlab bo'lmadi")
                except Exception as error:
                    LOG.exception(
                        "Hisobot jadvali foydalanuvchisi sozlanmadi (%s): %s",
                        user_id or "local",
                        error,
                    )

    def start_scheduler() -> None:
        nonlocal scheduler_thread
        scheduler_stop.clear()
        if not scheduler_thread or not scheduler_thread.is_alive():
            scheduler_thread = threading.Thread(
                target=scheduler_loop, name="dataflow-report-scheduler", daemon=True
            )
            scheduler_thread.start()

    def stop_scheduler() -> None:
        scheduler_stop.set()
        if scheduler_thread and scheduler_thread.is_alive():
            scheduler_thread.join(timeout=2)

    router.add_event_handler("startup", start_scheduler)
    router.add_event_handler("shutdown", stop_scheduler)

    def add_table(df: pd.DataFrame, filename: str) -> dict:
        if df.empty:
            raise HTTPException(400, "Ma'lumot topilmadi (jadval bo'sh)")
        file_id = uuid4().hex
        item = {
            "filename": filename,
            "table": make_table_name(filename),
            "versions": [{"label": "Asl nusxa", "df": df}],
        }
        files[file_id] = item
        save_version(file_id, 0, df)
        save_meta(file_id, item)
        return {"file_id": file_id, "table": item["table"], "rows": len(df), "columns": len(df.columns)}

    @router.get("/extras.js", include_in_schema=False)
    def extras_js():
        if not JS_FILE.is_file():
            raise HTTPException(404, f"Fayl topilmadi: {JS_FILE}")
        return FileResponse(JS_FILE, media_type="application/javascript")

    # ---------- hisobot va eksport ----------

    @router.get("/report-settings")
    def get_report_settings():
        return read_report_settings()

    @router.put("/report-settings")
    def update_report_settings(req: ReportSettingsIn, request: Request):
        guard(request)
        title = req.title.strip()
        if not title or len(title) > 120:
            raise HTTPException(400, "Hisobot sarlavhasi 1–120 belgi bo'lishi kerak")
        try:
            parsed_time = datetime_time.fromisoformat(req.schedule_time)
        except ValueError as error:
            raise HTTPException(400, "Kunlik yangilash vaqti HH:MM formatida bo'lishi kerak") from error
        if parsed_time.second or parsed_time.microsecond:
            raise HTTPException(400, "Vaqtni HH:MM formatida kiriting")
        logo = req.logo.strip()
        if logo:
            match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", logo)
            if not match:
                raise HTTPException(400, "Logotip PNG, JPEG yoki WebP formatida bo'lishi kerak")
            try:
                logo_bytes = base64.b64decode(match.group(2), validate=True)
            except ValueError as error:
                raise HTTPException(400, "Logotip ma'lumotini o'qib bo'lmadi") from error
            if len(logo_bytes) > 512 * 1024:
                raise HTTPException(413, "Logotip hajmi 512 KB dan oshmasin")
            signatures = {
                "png": logo_bytes.startswith(b"\x89PNG\r\n\x1a\n"),
                "jpeg": logo_bytes.startswith(b"\xff\xd8\xff"),
                "webp": len(logo_bytes) >= 12 and logo_bytes[:4] == b"RIFF" and logo_bytes[8:12] == b"WEBP",
            }
            if not signatures[match.group(1)]:
                raise HTTPException(400, "Logotip faylining haqiqiy formati mos kelmadi")
            try:
                with PILImage.open(io.BytesIO(logo_bytes)) as image:
                    if image.width > 4096 or image.height > 4096 or image.width * image.height > 16_000_000:
                        raise HTTPException(400, "Logotip o'lchami 4096 × 4096 pikseldan oshmasin")
                    image.verify()
            except HTTPException:
                raise
            except (OSError, SyntaxError, PILImage.DecompressionBombError) as error:
                raise HTTPException(400, "Logotip rasm fayli buzilgan yoki o'qilmaydi") from error
        previous = read_report_settings()
        settings = {
            **previous,
            "title": title,
            "logo": logo,
            "schedule_enabled": req.schedule_enabled,
            "schedule_time": parsed_time.strftime("%H:%M"),
            "auto_save": req.auto_save,
        }
        write_report_settings(settings)
        return settings

    @router.get("/reports/saved")
    def list_saved_reports():
        folder = saved_reports_dir()
        return [
            {"name": path.name, "bytes": path.stat().st_size}
            for path in sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            if path.is_file() and path.suffix in (".xlsx", ".html")
        ][:30]

    @router.post("/reports/refresh")
    def refresh_reports_now(request: Request):
        guard(request)
        settings = read_report_settings()
        try:
            refresh_reports(settings, force_save=True)
        except Exception as error:
            LOG.exception("Hisobotlarni hozir yangilash bajarilmadi")
            raise HTTPException(500, f"Hisobotlarni yangilab bo'lmadi: {type(error).__name__}: {str(error)[:250]}") from error
        return {"updated": len(files), "last_run": settings["last_run"]}

    @router.get("/reports/saved/{name}")
    def download_saved_report(name: str):
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,180}\.(xlsx|html)", name):
            raise HTTPException(400, "Hisobot fayli nomi noto'g'ri")
        path = saved_reports_dir() / name
        if not path.is_file() or path.parent.resolve() != saved_reports_dir().resolve():
            raise HTTPException(404, "Saqlangan hisobot topilmadi")
        media_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if path.suffix == ".xlsx" else "text/html; charset=utf-8"
        )
        return FileResponse(path, filename=name, media_type=media_type)

    @router.get("/templates")
    def list_templates():
        return TEMPLATES

    @router.post("/templates/{template_id}/run")
    def run_template(template_id: str, req: TemplateRunIn):
        template = next((item for item in TEMPLATES if item["id"] == template_id), None)
        if template is None:
            raise HTTPException(404, "Shablon topilmadi")
        item = get_item(req.file_id)
        raw_df = item["versions"][-1]["df"]
        typed = typed_frame(raw_df)
        schema = describe_dataframe(raw_df)["columns"]
        try:
            generated = template_result(template_id, req.columns, schema)
            sql = check_sql(generated["sql"])
            columns, rows, truncated = run_query_tables({"data": typed}, sql, 1000)
        except SandboxUnavailableError as error:
            raise HTTPException(503, str(error)) from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        except AIError as error:
            raise HTTPException(400, str(error)) from error
        except duckdb.Error as error:
            raise HTTPException(400, f"Shablon SQL xatosi: {str(error)[:300]}") from error
        return {
            **generated,
            "columns": columns,
            "rows": rows,
            "truncated": truncated,
        }

    @router.get("/files/{file_id}/report.html")
    def report_html(file_id: str):
        item = get_item(file_id)
        name = f"{Path(item['filename']).stem}_hisobot.html"
        return Response(
            build_report(item, read_report_settings()).encode("utf-8"),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": disposition(name)},
        )

    @router.get("/files/{file_id}/download.xlsx")
    def download_xlsx(file_id: str):
        item = get_item(file_id)
        name = f"{Path(item['filename']).stem}_hisobot.xlsx"
        return Response(
            build_xlsx(item, read_report_settings()),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": disposition(name)},
        )

    # ---------- g'ayritabiiy qiymatlar ----------

    @router.post("/files/{file_id}/outliers")
    def outliers(file_id: str, req: OutIn, request: Request):
        if req.action != "preview":
            guard(request)
        item = get_item(file_id)
        df = item["versions"][-1]["df"]
        if req.column not in df.columns:
            raise HTTPException(400, f"Ustun topilmadi: {req.column}")
        k = min(max(req.k, 0.5), 10.0)
        s = typed_frame(df)[req.column]
        if not pd.api.types.is_numeric_dtype(s.dtype):
            raise HTTPException(400, "Bu ustun raqamli emas")
        nums = s.dropna()
        if len(nums) < 4:
            raise HTTPException(400, "Ma'lumot yetarli emas")
        q1, q3 = nums.quantile(0.25), nums.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            raise HTTPException(400, "Qiymatlar deyarli bir xil (IQR = 0), bu usul mos emas")
        lo, hi = float(q1 - k * iqr), float(q3 + k * iqr)
        mask = (s < lo) | (s > hi)
        count = int(mask.sum())
        info = {
            "count": count,
            "total": int(len(nums)),
            "pct": round(count * 100 / len(nums), 2),
            "lo": round(lo, 4),
            "hi": round(hi, 4),
            "examples": [round(float(v), 4) for v in s[mask].head(8)],
            "applied": False,
        }
        if req.action == "preview" or count == 0:
            return info
        new = df.copy()
        if req.action == "clip":
            new.loc[s.index[(s < lo).to_numpy()], req.column] = num_str(lo)
            new.loc[s.index[(s > hi).to_numpy()], req.column] = num_str(hi)
            label = f"'{req.column}': {count} ta g'ayritabiiy qiymat chegaraga keltirildi (k={k})"
        else:
            new = new[~mask.to_numpy()]
            label = f"'{req.column}': g'ayritabiiy qiymatli {count} ta qator olib tashlandi (k={k})"
        item["versions"].append({"label": label, "df": new})
        save_version(file_id, len(item["versions"]) - 1, new)
        save_meta(file_id, item)
        return {**info, "applied": True, "rows": len(new), "label": label}

    # ---------- manbalardan yuklash ----------

    @router.post("/import/url")
    def import_url(req: UrlIn, request: Request):
        guard(request)
        url = req.url.strip()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise HTTPException(400, "To'liq havola kiriting (http:// yoki https://)")
        name = parsed.path.rsplit("/", 1)[-1] or parsed.netloc
        m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
        if m:
            qs = urllib.parse.parse_qs(parsed.query)
            frag = urllib.parse.parse_qs(parsed.fragment)
            gid = re.sub(r"\D", "", (qs.get("gid") or frag.get("gid") or ["0"])[0]) or "0"
            url = f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv&gid={gid}"
            name = f"google_sheet_{m.group(1)[:8]}.csv"
        if not name.lower().endswith((".csv", ".xlsx")):
            name += ".csv"
        try:
            http_req = urllib.request.Request(url, headers={"User-Agent": "DataFlowAI/1.0"})
            with urllib.request.urlopen(http_req, timeout=30) as resp:
                data = resp.read(MAX_DOWNLOAD + 1)
        except Exception as e:
            raise HTTPException(
                400,
                f"Yuklab bo'lmadi: {type(e).__name__}: {str(e)[:150]}. "
                "Google Sheets uchun 'Havolasi bor har kim ko'ra oladi' ruxsati kerak",
            )
        if len(data) > MAX_DOWNLOAD:
            raise HTTPException(413, "Fayl 20 MB dan katta")
        if data[:300].lstrip().lower().startswith((b"<!doctype", b"<html")):
            raise HTTPException(400, "Havola ochiq emas (kirish talab qilinadi) yoki fayl emas")
        try:
            if name.lower().endswith(".xlsx"):
                df = pd.read_excel(io.BytesIO(data), dtype=str)
            else:
                try:
                    df = pd.read_csv(io.BytesIO(data), dtype=str)
                except UnicodeDecodeError:
                    df = pd.read_csv(io.BytesIO(data), dtype=str, encoding="latin-1")
        except Exception:
            raise HTTPException(400, "Fayl formatini o'qib bo'lmadi (CSV yoki Excel bo'lishi kerak)")
        return add_table(df, name)

    @router.post("/import/db")
    def import_db(req: DbIn, request: Request):
        guard(request)
        try:
            sql = check_sql(req.query)
        except AIError as e:
            raise HTTPException(400, str(e))
        port = req.port or (5432 if req.kind == "postgres" else 3306)
        try:
            if req.kind == "postgres":
                import psycopg2

                conn = psycopg2.connect(
                    host=req.host, port=port, user=req.user, password=req.password,
                    dbname=req.database, connect_timeout=10,
                )
                conn.set_session(readonly=True)
            else:
                import pymysql

                conn = pymysql.connect(
                    host=req.host, port=port, user=req.user, password=req.password,
                    database=req.database, connect_timeout=10, read_timeout=60,
                )
        except ImportError:
            pkg = "psycopg2-binary" if req.kind == "postgres" else "pymysql"
            raise HTTPException(400, f"Kutubxona o'rnatilmagan. Terminalda: pip install {pkg}")
        except Exception as e:
            raise HTTPException(400, f"Ulanib bo'lmadi: {type(e).__name__}: {str(e)[:200]}")
        try:
            cur = conn.cursor()
            if req.kind == "mysql":
                cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.execute(sql)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(MAX_DB_ROWS + 1)
        except Exception as e:
            raise HTTPException(400, f"So'rov bajarilmadi: {type(e).__name__}: {str(e)[:200]}")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        truncated = len(rows) > MAX_DB_ROWS
        raw = pd.DataFrame(rows[:MAX_DB_ROWS], columns=cols)
        df = raw.astype(object).where(raw.notna(), None).map(lambda v: None if v is None else str(v))
        result = add_table(df, f"{req.kind}_{req.database}.csv")
        result["truncated"] = truncated
        return result

    # ---------- zaxira nusxa ----------

    def backup_candidates():
        for base in ("backend", "frontend", "workspace", "docs", "test-data"):
            folder = ROOT / base
            if not folder.exists():
                continue
            for p in folder.rglob("*"):
                if not p.is_file() or p.name == ".env":
                    continue
                if set(p.relative_to(ROOT).parts) & SKIP_DIRS:
                    continue
                yield p

    @router.post("/backup")
    def make_backup(request: Request):
        guard(request)
        BACKUPS.mkdir(exist_ok=True)
        path = BACKUPS / f"dataflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        count = 0
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for p in backup_candidates():
                try:
                    z.write(p, p.relative_to(ROOT).as_posix())
                    count += 1
                except OSError:
                    continue
        return {"name": path.name, "path": str(path), "files": count, "mb": round(path.stat().st_size / 1048576, 2)}

    @router.get("/backups")
    def list_backups():
        if not BACKUPS.exists():
            return []
        items = sorted(BACKUPS.glob("dataflow_*.zip"), reverse=True)[:10]
        return [{"name": p.name, "mb": round(p.stat().st_size / 1048576, 2)} for p in items]

    return router