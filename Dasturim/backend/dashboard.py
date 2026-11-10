import json
import html
from datetime import date, timedelta
from pathlib import Path
from typing import Callable
from uuid import uuid4

import duckdb
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ai import AIError, SandboxUnavailableError, check_sql, run_query_tables, typed_frame


class SavedItem(BaseModel):
    title: str
    type: str
    content: str


class PanelIn(BaseModel):
    title: str
    sql: str
    table: str | None = None
    chart: dict = {}
    kind: str = "chart"
    grid: dict = {}


class DashboardFilters(BaseModel):
    filters: list[dict] = []


class ReorderIn(BaseModel):
    panel_ids: list[str]


def make_router(files: dict, workspace: Path | Callable[[], Path]) -> APIRouter:
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    def current_workspace() -> Path:
        return workspace() if callable(workspace) else workspace

    def global_dash_file() -> Path:
        return current_workspace() / "dashboard.json"

    def filter_file() -> Path:
        return current_workspace() / "dashboard_filters.json"

    def read_filters() -> list[dict]:
        path = filter_file()
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise HTTPException(500, f"Dashboard filtrlari o'qilmadi: {e}") from e
        if not isinstance(data, list):
            raise HTTPException(500, "Dashboard filtrlari noto'g'ri formatda")
        return data

    def write_filters(filters: list[dict]) -> None:
        filter_file().parent.mkdir(parents=True, exist_ok=True)
        filter_file().write_text(json.dumps(filters, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_items(path: Path) -> list:
        if not path.is_file():
            return []
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise HTTPException(500, f"Dashboard faylini o'qib bo'lmadi: {e}") from e
        if not isinstance(items, list):
            raise HTTPException(500, "Dashboard fayli ro'yxat shaklida emas")
        return items

    def write_items(path: Path, items: list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            raise HTTPException(500, f"Dashboard faylini saqlab bo'lmadi: {e}") from e

    def filter_frames(filters: list[dict]) -> dict[str, object]:
        tables = {}
        for entry in files.values():
            frame = typed_frame(entry["versions"][-1]["df"])
            relevant = [f for f in filters if f.get("table") in (entry["table"], "data")]
            for rule in relevant:
                column = rule.get("column")
                if column not in frame.columns:
                    continue
                series = frame[column]
                if rule.get("values"):
                    frame = frame[series.astype(str).isin([str(v) for v in rule["values"]])]
                if rule.get("from") or rule.get("to"):
                    try:
                        if rule.get("from"):
                            dates = pd.to_datetime(frame[column], errors="coerce", format="mixed")
                            frame = frame[dates >= pd.Timestamp(date.fromisoformat(rule["from"]))]
                        if rule.get("to"):
                            dates = pd.to_datetime(frame[column], errors="coerce", format="mixed")
                            end = pd.Timestamp(date.fromisoformat(rule["to"]) + timedelta(days=1))
                            frame = frame[dates < end]
                    except (TypeError, ValueError) as e:
                        raise HTTPException(400, "Sana filtrining formati YYYY-MM-DD bo'lishi kerak") from e
            tables[entry["table"]] = frame
        return tables

    def execute_panel(item: dict, filters: list[dict] | None = None) -> dict:
        tables = filter_frames(filters or [])
        if item.get("table"):
            source = tables.get(item["table"])
            if source is None:
                raise HTTPException(404, "Panelga biriktirilgan jadval topilmadi")
            tables["data"] = source
        try:
            sql = check_sql(item.get("sql", ""))
            columns, rows, truncated = run_query_tables(tables, sql, limit=500)
        except SandboxUnavailableError as e:
            raise HTTPException(503, str(e)) from e
        except AIError as e:
            raise HTTPException(400, str(e)) from e
        except duckdb.Error as e:
            raise HTTPException(400, f"SQL xatosi: {str(e)[:400]}") from e
        return {"columns": columns, "rows": rows, "truncated": truncated}

    def get_dash_file(file_id: str) -> Path:
        if file_id not in files:
            raise HTTPException(404, "Jadval topilmadi")
        base = current_workspace()
        table_folder = base / "tables" / file_id
        legacy_folder = base / file_id
        return (legacy_folder if legacy_folder.exists() else table_folder) / "dashboard.json"

    @router.get("")
    def list_dashboard():
        return read_items(global_dash_file())

    @router.post("")
    def add_dashboard_panel(item: PanelIn):
        try:
            sql = check_sql(item.sql)
        except AIError as e:
            raise HTTPException(400, str(e)) from e
        if item.table and not any(f["table"] == item.table for f in files.values()):
            raise HTTPException(400, "Panelga biriktirilgan jadval topilmadi")
        saved = {
            "id": uuid4().hex,
            "title": item.title.strip() or "Yangi panel",
            "sql": sql,
            "table": item.table,
            "chart": item.chart,
            "kind": item.kind if item.kind in {"chart", "kpi", "table"} else "chart",
            "grid": item.grid,
        }
        items = read_items(global_dash_file())
        items.append(saved)
        write_items(global_dash_file(), items)
        return saved

    @router.put("/panels/{panel_id}")
    def update_dashboard_panel(panel_id: str, item: PanelIn):
        try:
            sql = check_sql(item.sql)
        except AIError as e:
            raise HTTPException(400, str(e)) from e
        if item.table and not any(f["table"] == item.table for f in files.values()):
            raise HTTPException(400, "Panelga biriktirilgan jadval topilmadi")
        items = read_items(global_dash_file())
        saved = next((entry for entry in items if entry.get("id") == panel_id), None)
        if saved is None:
            raise HTTPException(404, "Dashboard paneli topilmadi")
        saved.update({
            "title": item.title.strip() or "Yangi panel",
            "sql": sql,
            "table": item.table,
            "chart": item.chart,
            "kind": item.kind if item.kind in {"chart", "kpi", "table"} else "chart",
            "grid": item.grid,
        })
        write_items(global_dash_file(), items)
        return saved

    @router.post("/reorder")
    def reorder_dashboard_panels(req: ReorderIn):
        items = read_items(global_dash_file())
        by_id = {entry.get("id"): entry for entry in items}
        if len(req.panel_ids) != len(items) or set(req.panel_ids) != set(by_id):
            raise HTTPException(400, "Panel tartibi to'liq va takrorlanmagan bo'lishi kerak")
        ordered = [by_id[panel_id] for panel_id in req.panel_ids]
        write_items(global_dash_file(), ordered)
        return ordered

    @router.get("/filters")
    def dashboard_filter_options():
        options = []
        for entry in files.values():
            frame = typed_frame(entry["versions"][-1]["df"])
            for column in frame.columns:
                series = frame[column]
                if pd.api.types.is_datetime64_any_dtype(series.dtype):
                    options.append({
                        "table": entry["table"], "column": str(column), "kind": "date",
                        "min": str(series.min())[:10] if series.notna().any() else "",
                        "max": str(series.max())[:10] if series.notna().any() else "",
                    })
                elif not pd.api.types.is_numeric_dtype(series.dtype):
                    values = series.dropna().astype(str).value_counts().head(100).index.tolist()
                    options.append({"table": entry["table"], "column": str(column), "kind": "values", "values": values})
        return {"filters": read_filters(), "options": options}

    @router.put("/filters")
    def save_dashboard_filters(req: DashboardFilters):
        allowed = {(f["table"], f["column"]) for f in dashboard_filter_options()["options"]}
        for rule in req.filters:
            if (rule.get("table"), rule.get("column")) not in allowed:
                raise HTTPException(400, "Filtr uchun jadval yoki ustun topilmadi")
            if rule.get("kind") not in {"values", "date"}:
                raise HTTPException(400, "Filtr turi noto'g'ri")
            if rule["kind"] == "date":
                try:
                    start = date.fromisoformat(rule["from"]) if rule.get("from") else None
                    end = date.fromisoformat(rule["to"]) if rule.get("to") else None
                except (TypeError, ValueError) as e:
                    raise HTTPException(400, "Sana filtrining formati YYYY-MM-DD bo'lishi kerak") from e
                if start and end and start > end:
                    raise HTTPException(400, "Sana oralig'i noto'g'ri")
            elif not isinstance(rule.get("values"), list):
                raise HTTPException(400, "Qiymat filtrida tanlangan qiymatlar ro'yxati bo'lishi kerak")
        write_filters(req.filters)
        return {"filters": req.filters}

    @router.get("/export.html")
    def export_dashboard_html():
        items = read_items(global_dash_file())
        filters = read_filters()
        blocks = []
        for item in items:
            result = execute_panel(item, filters)
            headers = "".join(f"<th>{html.escape(str(c))}</th>" for c in result["columns"])
            rows = "".join(
                "<tr>" + "".join(f"<td>{html.escape(str(value if value is not None else ''))}</td>" for value in row) + "</tr>"
                for row in result["rows"]
            )
            blocks.append(
                f"<section><h2>{html.escape(str(item.get('title', 'Panel')))}</h2>"
                f"<p>{len(result['rows'])} qator</p><table><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></section>"
            )
        content = "<!doctype html><html lang='uz'><meta charset='utf-8'><title>DataFlow dashboard</title>" \
            "<style>body{font:14px Segoe UI,Arial;margin:24px;color:#172033}section{margin-bottom:24px;padding:16px;border:1px solid #ddd;border-radius:12px}table{border-collapse:collapse;width:100%}td,th{padding:7px;border-bottom:1px solid #ddd;text-align:left}</style>" \
            + "<h1>Dashboard</h1><p>Saqlangan filtrlar bilan eksport qilindi.</p>" + "".join(blocks) + "</html>"
        return Response(content, media_type="text/html; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="dashboard.html"'})

    @router.post("/{panel_id}/run")
    def run_dashboard_panel(panel_id: str):
        items = read_items(global_dash_file())
        item = next((entry for entry in items if entry.get("id") == panel_id), None)
        if item is None:
            raise HTTPException(404, "Dashboard paneli topilmadi")
        return execute_panel(item, read_filters())

    @router.delete("/{panel_id}")
    def delete_dashboard_panel(panel_id: str):
        path = global_dash_file()
        items = read_items(path)
        remaining = [entry for entry in items if entry.get("id") != panel_id]
        if len(remaining) == len(items):
            raise HTTPException(404, "Dashboard paneli topilmadi")
        write_items(path, remaining)
        return {"deleted": panel_id}

    # Eski per-jadval API'lari orqaga moslik uchun saqlangan.
    @router.get("/{file_id}")
    def get_legacy_dashboard(file_id: str):
        return read_items(get_dash_file(file_id))

    @router.post("/{file_id}")
    def save_legacy_dashboard(file_id: str, item: SavedItem):
        path = get_dash_file(file_id)
        items = read_items(path)
        items.append(item.model_dump())
        write_items(path, items)
        return {"saved": True, "total": len(items)}

    @router.delete("/{file_id}/{index}")
    def delete_legacy_dashboard_item(file_id: str, index: int):
        path = get_dash_file(file_id)
        items = read_items(path)
        if not 0 <= index < len(items):
            raise HTTPException(404, "Saqlangan element topilmadi")
        items.pop(index)
        write_items(path, items)
        return {"deleted": index}

    return router
