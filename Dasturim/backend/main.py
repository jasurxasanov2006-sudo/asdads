import json
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import zipfile
from collections.abc import MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import uuid4

import duckdb
import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from ai import (
    AIError,
    SandboxUnavailableError,
    ask_question,
    check_query_budget,
    check_sql,
    explain_sql,
    generate_insights,
    get_runtime_settings,
    recent_questions,
    record_recent_question,
    run_query_tables,
    suggest_cleaning_steps,
    typed_frame,
)
from cleaning import CleanError, apply_action, near_duplicate_groups
from profiling import profile_dataframe
from stats import describe_dataframe
from security import CURRENT_USER, auth_middleware, current_user_id, make_router as make_auth_router

logging.basicConfig(
    level=os.getenv("DATAFLOW_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="DataFlow AI")
cors_origins = [
    origin.strip() for origin in os.getenv("DATAFLOW_CORS_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Dataflow", "X-CSRF-Token"],
    allow_credentials=True,
)
app.middleware("http")(auth_middleware)

MAX_SIZE = 1024 * 1024 * 1024
SQL_MAX_ROWS = 1000
PAGE_SIZE_DEFAULT = 100
PAGE_SIZE_MAX = 1000

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
FRONTEND_FILE = ROOT / "frontend" / "index.html"
WORKSPACE = Path(os.getenv("DATAFLOW_DATA_DIR", str(ROOT / "workspace"))).expanduser().resolve()
WORKSPACE.mkdir(exist_ok=True)
PROJECTS_DIR = WORKSPACE / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_PROJECT_ID = "default"
ACTIVE_PROJECT_ID = DEFAULT_PROJECT_ID
_ACTIVE_PROJECT_CONTEXT = ContextVar("dataflow_active_project", default=None)
_USER_FILES: dict[str, dict[str, dict]] = {}
_WORKSPACE_LOCK = threading.RLock()
_LOADED_USERS: set[str] = set()


class UserFiles(MutableMapping):
    def _store(self):
        return _USER_FILES.setdefault(current_user_id(), {})

    def __getitem__(self, key):
        return self._store()[key]

    def __setitem__(self, key, value):
        self._store()[key] = value

    def __delitem__(self, key):
        del self._store()[key]

    def __iter__(self):
        return iter(self._store())

    def __len__(self):
        return len(self._store())

    def clear(self):
        self._store().clear()


# file_id -> {"filename", "table", "versions": [{"label", "df"}]}; [0] - asl nusxa
FILES = UserFiles()


def workspace_root() -> Path:
    user_id = current_user_id()
    owner_file = WORKSPACE / "workspace_owner.json"
    if user_id == "local":
        return WORKSPACE
    if owner_file.is_file():
        try:
            if json.loads(owner_file.read_text(encoding="utf-8")).get("user_id") == user_id:
                return WORKSPACE
        except (OSError, json.JSONDecodeError):
            raise RuntimeError("Workspace egasi ma'lumotini o'qib bo'lmadi")
    return WORKSPACE / "users" / user_id


def active_project_id() -> str:
    return _ACTIVE_PROJECT_CONTEXT.get() or ACTIVE_PROJECT_ID


def set_active_project(project_id: str) -> None:
    global ACTIVE_PROJECT_ID
    _ACTIVE_PROJECT_CONTEXT.set(project_id)
    if current_user_id() == "local":
        ACTIVE_PROJECT_ID = project_id


def initialize_user_workspace(user_id: str, bootstrap_owner: bool = False) -> None:
    user_token = CURRENT_USER.set(user_id)
    try:
        if bootstrap_owner:
            marker = WORKSPACE / "workspace_owner.json"
            owner_id = None
            if marker.exists():
                owner_id = json.loads(marker.read_text(encoding="utf-8")).get("user_id")
            if owner_id != user_id:
                from security import list_users

                known_users = {user["id"] for user in list_users()}
                if not isinstance(owner_id, str) or owner_id not in known_users:
                    replacement = marker.with_suffix(".tmp")
                    replacement.write_text(json.dumps({"user_id": user_id}), encoding="utf-8")
                    replacement.replace(marker)
        with _WORKSPACE_LOCK:
            current_root = workspace_root()
            current_root.mkdir(parents=True, exist_ok=True)
            active_path = current_root / "active_project.json"
            if user_id not in _LOADED_USERS:
                if not (project_dir(DEFAULT_PROJECT_ID) / "project.json").is_file():
                    write_project(DEFAULT_PROJECT_ID, "Mening loyiham")
                    active_path.write_text(json.dumps({"id": DEFAULT_PROJECT_ID}), encoding="utf-8")
                try:
                    stored = json.loads(active_path.read_text(encoding="utf-8")).get("id")
                except (OSError, json.JSONDecodeError):
                    stored = DEFAULT_PROJECT_ID
                valid = stored == DEFAULT_PROJECT_ID or (
                    isinstance(stored, str) and re.fullmatch(r"[0-9a-f]{32}", stored)
                )
                _ACTIVE_PROJECT_CONTEXT.set(
                    stored if valid and (project_dir(stored) / "project.json").is_file() else DEFAULT_PROJECT_ID
                )
                load_workspace()
                _LOADED_USERS.add(user_id)
            else:
                try:
                    stored = json.loads(active_path.read_text(encoding="utf-8")).get("id")
                except (OSError, json.JSONDecodeError):
                    stored = DEFAULT_PROJECT_ID
                valid = stored == DEFAULT_PROJECT_ID or (
                    isinstance(stored, str) and re.fullmatch(r"[0-9a-f]{32}", stored)
                )
                if not valid or not (project_dir(stored) / "project.json").is_file():
                    stored = DEFAULT_PROJECT_ID
                    if not (project_dir(stored) / "project.json").is_file():
                        write_project(stored, "Mening loyiham")
                    active_path.write_text(json.dumps({"id": stored}), encoding="utf-8")
                _ACTIVE_PROJECT_CONTEXT.set(stored)
    finally:
        CURRENT_USER.reset(user_token)


@contextmanager
def user_workspace_context(user_id: str):
    user_token = CURRENT_USER.set(user_id)
    project_token = _ACTIVE_PROJECT_CONTEXT.set(None)
    try:
        initialize_user_workspace(user_id)
        yield
    finally:
        _ACTIVE_PROJECT_CONTEXT.reset(project_token)
        CURRENT_USER.reset(user_token)


def workspace_user_ids() -> list[str]:
    from security import auth_enabled, list_users

    if not auth_enabled():
        return []
    return [user["id"] for user in list_users() if user["enabled"]]


# ---------- saqlash (disk) ----------

def projects_root() -> Path:
    return workspace_root() / "projects"


def project_dir(project_id: str | None = None) -> Path:
    return projects_root() / (project_id or active_project_id())


def tables_dir(project_id: str | None = None) -> Path:
    path = project_dir(project_id) / "tables"
    path.mkdir(parents=True, exist_ok=True)
    return path


def table_dir(file_id: str) -> Path:
    return tables_dir() / file_id


def get_project(project_id: str) -> dict:
    if project_id != DEFAULT_PROJECT_ID and not re.fullmatch(r"[0-9a-f]{32}", project_id):
        raise HTTPException(404, "Loyiha topilmadi")
    path = project_dir(project_id) / "project.json"
    if not path.is_file():
        raise HTTPException(404, "Loyiha topilmadi")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(500, f"Loyiha ma'lumotini o'qib bo'lmadi: {e}") from e
    return data


def list_projects() -> list[dict]:
    result = []
    root = projects_root()
    root.mkdir(parents=True, exist_ok=True)
    for folder in sorted(root.iterdir(), key=lambda p: p.name):
        project_file = folder / "project.json"
        if not folder.is_dir() or not project_file.is_file():
            continue
        try:
            data = json.loads(project_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise HTTPException(500, f"Loyiha ma'lumotini o'qib bo'lmadi ({folder.name}): {e}") from e
        result.append({
            "id": data["id"],
            "name": data["name"],
            "active": data["id"] == active_project_id(),
        })
    return result


def write_project(project_id: str, name: str) -> None:
    path = project_dir(project_id)
    path.mkdir(parents=True, exist_ok=True)
    (path / "project.json").write_text(
        json.dumps({"id": project_id, "name": name}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        con.register("dataflow_frame", df)
        escaped = str(path).replace("'", "''")
        con.execute(f"COPY dataflow_frame TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        con.close()


def read_parquet_frame(path: Path) -> pd.DataFrame:
    escaped = str(path).replace("'", "''")
    con = duckdb.connect()
    try:
        return con.execute(f"SELECT * FROM read_parquet('{escaped}')").df()
    finally:
        con.close()


def migrate_workspace() -> None:
    """Move the old single-workspace layout into a default project and convert CSV versions."""
    global ACTIVE_PROJECT_ID
    root = workspace_root()
    projects_root().mkdir(parents=True, exist_ok=True)
    active_file = root / "active_project.json"
    if active_file.is_file():
        try:
            candidate = json.loads(active_file.read_text(encoding="utf-8")).get("id")
            valid_id = candidate == DEFAULT_PROJECT_ID or (
                isinstance(candidate, str) and re.fullmatch(r"[0-9a-f]{32}", candidate)
            )
            if valid_id and (project_dir(candidate) / "project.json").is_file():
                ACTIVE_PROJECT_ID = candidate
        except (OSError, json.JSONDecodeError):
            pass

    default_dir = project_dir(DEFAULT_PROJECT_ID)
    write_project(DEFAULT_PROJECT_ID, "Mening loyiham")
    default_tables = tables_dir(DEFAULT_PROJECT_ID)

    for child in list(root.iterdir()):
        if child.name in {"projects", "active_project.json", "recipes", "dashboard.json", "notebook.json"}:
            continue
        if not child.is_dir() or not (child / "meta.json").is_file():
            continue
        target = default_tables / child.name
        if target.exists():
            continue
        shutil.move(str(child), str(target))

    for name in ("recipes", "dashboard.json", "notebook.json"):
        source = root / name
        target = default_dir / name
        if source.exists() and not target.exists():
            shutil.move(str(source), str(target))

    for folder in projects_root().iterdir():
        if not folder.is_dir():
            continue
        for data_dir in (folder / "tables").glob("*"):
            meta_path = data_dir / "meta.json"
            if not meta_path.is_file():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                labels = meta.get("labels", [])
                for index in range(len(labels)):
                    parquet_path = data_dir / f"v{index}.parquet"
                    csv_path = data_dir / f"v{index}.csv"
                    if parquet_path.is_file():
                        continue
                    if not csv_path.is_file():
                        raise FileNotFoundError(f"Versiya fayli topilmadi: {csv_path.name}")
                    con = duckdb.connect()
                    try:
                        escaped = str(csv_path).replace("'", "''")
                        parquet_target = str(parquet_path).replace("'", "''")
                        con.execute(
                            f"COPY (SELECT * FROM read_csv('{escaped}', all_varchar=true, "
                            "header=true, null_padding=true)) "
                            f"TO '{parquet_target}' (FORMAT PARQUET, COMPRESSION ZSTD)"
                        )
                    finally:
                        con.close()
                    csv_path.unlink()
                meta["storage"] = "parquet"
                meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            except (OSError, ValueError, duckdb.Error) as e:
                raise RuntimeError(f"Workspace migratsiyasi bajarilmadi ({data_dir.name}): {e}") from e

    active_file.write_text(json.dumps({"id": active_project_id()}), encoding="utf-8")


def save_version(file_id: str, index: int, df: pd.DataFrame) -> None:
    folder = table_dir(file_id)
    folder.mkdir(parents=True, exist_ok=True)
    write_parquet(folder / f"v{index}.parquet", df)


def save_meta(file_id: str, item: dict) -> None:
    meta = {
        "filename": item["filename"],
        "table": item["table"],
        "labels": [v["label"] for v in item["versions"]],
        "storage": "parquet",
    }
    (table_dir(file_id) / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )


def load_workspace() -> None:
    FILES.clear()
    folders = [p for p in tables_dir().iterdir() if p.is_dir()]
    for folder in sorted(folders, key=lambda p: p.stat().st_mtime):
        meta_file = folder / "meta.json"
        if not meta_file.is_file():
            continue
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            versions = []
            for i, label in enumerate(meta["labels"]):
                df = read_parquet_frame(folder / f"v{i}.parquet")
                versions.append({"label": label, "df": df})
            FILES[folder.name] = {
                "filename": meta["filename"],
                "table": meta["table"],
                "versions": versions,
            }
        except (OSError, ValueError, KeyError) as e:
            raise RuntimeError(f"Jadvalni yuklab bo'lmadi ({folder.name}): {e}") from e


def make_table_name(filename: str) -> str:
    stem = re.sub(r"[^0-9a-zA-Z_]+", "_", Path(filename).stem).strip("_").lower() or "jadval"
    if stem[0].isdigit():
        stem = "t_" + stem
    used = {item["table"] for item in FILES.values()}
    name, n = stem, 2
    while name in used or name == "data":
        name = f"{stem}_{n}"
        n += 1
    return name


migrate_workspace()
load_workspace()
app.state.workspace_initializer = initialize_user_workspace
app.state.workspace_owner_initializer = lambda user_id: initialize_user_workspace(
    user_id, bootstrap_owner=True
)
app.include_router(make_auth_router())


# ---------- modellar ----------

class Action(BaseModel):
    type: Literal[
        "remove_duplicates",
        "remove_near_duplicates",
        "trim_text",
        "normalize_text",
        "drop_missing_rows",
        "fill_missing",
        "fill_missing_unknown",
        "invalid_to_empty",
        "convert_number",
        "convert_date",
        "date_to_iso",
        "rename_column",
        "drop_column",
        "split_column",
        "merge_columns",
        "replace_values",
    ]
    column: str | None = None
    method: Literal["median", "mean", "mode", "value"] | None = None
    value: str | None = None
    columns: list[str] | None = None
    mode: str | None = None
    new_name: str | None = None
    second_column: str | None = None
    target_column: str | None = None
    separator: str | None = None
    drop_sources: bool = False
    replacements: dict[str, str] | None = None
    decimal_separator: str = "."
    thousands_separator: str | None = None
    date_format: str | None = None


class CleanRequest(BaseModel):
    actions: list[Action]
    dry_run: bool = False  # True bo'lsa, faqat natijani ko'rsatadi, saqlamaydi


class RecipeIn(BaseModel):
    name: str
    actions: list[Action]


class ApplyRecipeRequest(BaseModel):
    dry_run: bool = False


class NearDuplicatesRequest(BaseModel):
    columns: list[str]


class AskRequest(BaseModel):
    question: str
    table_ids: list[str] = []
    explain: bool = False


class AISettingsRequest(BaseModel):
    provider: str | None = None
    send_sample: bool | None = None
    history_limit: int | None = None
    query_limit: int | None = None


class InsightRequest(BaseModel):
    limit: int = 3


class SqlRequest(BaseModel):
    sql: str
    active_id: str | None = None
    explain: bool = False
    error: str = ""


class ProjectIn(BaseModel):
    name: str


class PivotRequest(BaseModel):
    rows: list[str]
    columns: list[str] = []
    values: str
    aggregation: Literal["sum", "count", "mean", "min", "max"] = "sum"


# ---------- yordamchi ----------

def get_item(file_id: str) -> dict:
    item = FILES.get(file_id)
    if item is None:
        raise HTTPException(404, "Jadval topilmadi. Uni qayta yuklang")
    return item


def make_preview(df: pd.DataFrame) -> list[dict]:
    head = df.head(10).astype(object)
    return head.where(head.notna(), None).to_dict(orient="records")


def apply_cleaning(
    file_id: str, item: dict, actions: list[Action], dry_run: bool, label: str | None = None
) -> dict:
    current = item["versions"][-1]["df"]
    before_profile = profile_dataframe(current)
    df = current
    changes = []
    try:
        for index, action in enumerate(actions, 1):
            try:
                df, message = apply_action(df, action)
            except CleanError as e:
                prefix = f"{label}ning {index}-qadami: " if label else ""
                raise HTTPException(400, prefix + str(e)) from e
            changes.append(message)
    except HTTPException:
        raise

    after_profile = profile_dataframe(df)
    if not dry_run:
        version_label = label or "; ".join(changes) or "Bo'sh tozalash qadami"
        item["versions"].append({"label": version_label, "df": df})
        save_version(file_id, len(item["versions"]) - 1, df)
        save_meta(file_id, item)

    return {
        "applied": not dry_run,
        "changes": changes,
        "before": {
            "rows": len(current),
            "issues": before_profile["summary"]["issues"],
            "preview": make_preview(current),
        },
        "after": {
            "rows": len(df),
            "issues": after_profile["summary"]["issues"],
            "preview": make_preview(df),
        },
        "report": after_profile,
        "preview": make_preview(df),
    }


# ---------- sahifa va holat ----------

@app.get("/health")
def health():
    from security import auth_enabled, has_users

    return {"status": "ok", "auth_configured": has_users(), "auth_enabled": auth_enabled()}


@app.get("/projects")
def projects():
    return {"active_id": active_project_id(), "projects": list_projects()}


@app.post("/projects")
def create_project(req: ProjectIn):
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "Loyiha nomini kiriting")
    if len(name) > 80:
        raise HTTPException(400, "Loyiha nomi 80 belgidan oshmasin")
    project_id = uuid4().hex
    write_project(project_id, name)
    set_active_project(project_id)
    (workspace_root() / "active_project.json").write_text(
        json.dumps({"id": project_id}), encoding="utf-8"
    )
    load_workspace()
    return {"active_id": active_project_id(), "projects": list_projects()}


@app.post("/projects/{project_id}/activate")
def activate_project(project_id: str):
    get_project(project_id)
    set_active_project(project_id)
    (workspace_root() / "active_project.json").write_text(
        json.dumps({"id": project_id}), encoding="utf-8"
    )
    load_workspace()
    return {"active_id": active_project_id(), "projects": list_projects()}


@app.get("/settings")
def get_settings():
    return get_runtime_settings()


@app.post("/settings")
def save_settings(req: AISettingsRequest):
    payload = {}
    if req.provider is not None:
        payload["provider"] = req.provider
    if req.send_sample is not None:
        payload["send_sample"] = req.send_sample
    if req.history_limit is not None:
        payload["history_limit"] = req.history_limit
    if req.query_limit is not None:
        payload["query_limit"] = req.query_limit
    try:
        from ai import set_runtime_settings

        return set_runtime_settings(payload)
    except Exception as e:
        raise HTTPException(400, f"Sozlamalarni saqlab bo'lmadi: {e}") from e


@app.get("/", include_in_schema=False)
def index():
    if not FRONTEND_FILE.is_file():
        raise HTTPException(404, f"Interfeys fayli topilmadi: {FRONTEND_FILE}")
    return FileResponse(FRONTEND_FILE)


@app.get("/charts.js", include_in_schema=False)
def charts_js():
    path = ROOT / "frontend" / "charts.js"
    if not path.is_file():
        raise HTTPException(404, f"Fayl topilmadi: {path}")
    return FileResponse(path, media_type="application/javascript")


@app.get("/dashboard.js", include_in_schema=False)
def dashboard_js():
    path = ROOT / "frontend" / "dashboard.js"
    if not path.is_file():
        raise HTTPException(404, f"Fayl topilmadi: {path}")
    return FileResponse(path, media_type="application/javascript")


@app.get("/auth.js", include_in_schema=False)
def auth_js():
    path = ROOT / "frontend" / "auth.js"
    if not path.is_file():
        raise HTTPException(404, f"Fayl topilmadi: {path}")
    return FileResponse(path, media_type="application/javascript")


@app.get("/i18n.js", include_in_schema=False)
def i18n_js():
    path = ROOT / "frontend" / "i18n.js"
    if not path.is_file():
        raise HTTPException(404, f"Fayl topilmadi: {path}")
    return FileResponse(path, media_type="application/javascript")


# ---------- jadvallar ----------

@app.get("/files")
def list_files():
    out = []
    for file_id, item in FILES.items():
        df = item["versions"][-1]["df"]
        out.append(
            {
                "file_id": file_id,
                "filename": item["filename"],
                "table": item["table"],
                "rows": len(df),
                "columns": [str(c) for c in df.columns],
                "versions": len(item["versions"]),
                "storage": "Parquet",
            }
        )
    return out


@app.post("/upload/sheets")
async def upload_sheets(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(400, "Varaqlar ro'yxati faqat .xlsx fayl uchun mavjud")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            temp_path = Path(tmp.name)
            size = 0
            while chunk := await file.read(8 * 1024 * 1024):
                size += len(chunk)
                if size > MAX_SIZE:
                    raise HTTPException(413, "Fayl 1 GB dan katta")
                tmp.write(chunk)
        workbook = pd.ExcelFile(temp_path, engine="openpyxl")
        try:
            sheets = workbook.sheet_names
        finally:
            workbook.close()
        return {"sheets": sheets}
    except HTTPException:
        raise
    except (OSError, ValueError, zipfile.BadZipFile, InvalidFileException) as e:
        raise HTTPException(400, f"Excel varaqlarini o'qib bo'lmadi: {str(e)[:200]}") from e
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        await file.close()


@app.post("/upload")
async def upload(file: UploadFile = File(...), sheets: str | None = Form(None)):
    name = (file.filename or "").lower()
    if not name.endswith((".csv", ".xlsx")):
        raise HTTPException(400, "Faqat .csv va .xlsx fayllar qabul qilinadi")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(name).suffix) as tmp:
            temp_path = Path(tmp.name)
            size = 0
            while chunk := await file.read(8 * 1024 * 1024):
                size += len(chunk)
                if size > MAX_SIZE:
                    raise HTTPException(413, "Fayl 1 GB dan katta")
                tmp.write(chunk)

        if name.endswith(".csv"):
            path = str(temp_path).replace("'", "''")
            con = duckdb.connect()
            try:
                try:
                    df = con.execute(
                        f"SELECT * FROM read_csv('{path}', all_varchar=true, "
                        "header=true, null_padding=true)"
                    ).df()
                except duckdb.Error:
                    df = con.execute(
                        f"SELECT * FROM read_csv('{path}', all_varchar=true, "
                        "header=true, null_padding=true, encoding='latin-1')"
                    ).df()
            finally:
                con.close()
            sheet_frames = [(file.filename or "jadval.csv", df)]
        else:
            workbook = pd.ExcelFile(temp_path, engine="openpyxl")
            try:
                requested = json.loads(sheets) if sheets else [workbook.sheet_names[0]]
                if requested == ["__all__"]:
                    requested = workbook.sheet_names
                if not isinstance(requested, list) or not requested:
                    raise HTTPException(400, "Kamida bitta Excel varag'ini tanlang")
                unknown = [sheet for sheet in requested if sheet not in workbook.sheet_names]
                if unknown:
                    raise HTTPException(400, f"Excel varag'i topilmadi: {unknown[0]}")
                sheet_frames = [
                    (f"{Path(file.filename or 'excel').stem}_{sheet}.xlsx",
                     pd.read_excel(workbook, sheet_name=sheet, dtype=str))
                    for sheet in requested
                ]
            finally:
                workbook.close()

        results = []
        for filename, df in sheet_frames:
            if df.empty:
                raise HTTPException(400, f"'{filename}' faylida ma'lumot yo'q")
            file_id = uuid4().hex
            item = {
                "filename": filename,
                "table": make_table_name(filename),
                "versions": [{"label": "Asl nusxa", "df": df}],
            }
            FILES[file_id] = item
            save_version(file_id, 0, df)
            save_meta(file_id, item)
            results.append({
                "file_id": file_id,
                "filename": filename,
                "table": item["table"],
                **profile_dataframe(df),
                "preview": make_preview(df),
            })
        return results[0] if len(results) == 1 else {"tables": results}
    except HTTPException:
        raise
    except (
        OSError,
        ValueError,
        zipfile.BadZipFile,
        InvalidFileException,
        duckdb.Error,
        pd.errors.ParserError,
    ) as e:
        raise HTTPException(400, f"Faylni o'qib bo'lmadi: {str(e)[:250]}") from e
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        await file.close()


@app.delete("/files/{file_id}")
def delete_file(file_id: str):
    get_item(file_id)
    del FILES[file_id]
    shutil.rmtree(table_dir(file_id), ignore_errors=True)
    return {"deleted": file_id}


@app.get("/files/{file_id}/rows")
def file_rows(
    file_id: str,
    offset: int = 0,
    limit: int = PAGE_SIZE_DEFAULT,
    sort: str | None = None,
    direction: Literal["asc", "desc"] = "asc",
):
    item = get_item(file_id)
    if offset < 0:
        raise HTTPException(400, "Sahifa boshlanishi manfiy bo'lmasin")
    limit = min(max(limit, 1), PAGE_SIZE_MAX)
    df = item["versions"][-1]["df"]
    if sort is not None and sort not in df.columns:
        raise HTTPException(400, f"Ustun topilmadi: {sort}")
    path = table_dir(file_id) / f"v{len(item['versions']) - 1}.parquet"
    escaped_path = str(path).replace("'", "''")
    order = ""
    if sort:
        escaped_column = sort.replace('"', '""')
        order = f' ORDER BY "{escaped_column}" {direction.upper()} NULLS LAST'
    con = duckdb.connect()
    try:
        columns = [str(c) for c in df.columns]
        rows = con.execute(
            f"SELECT * FROM read_parquet('{escaped_path}'){order} LIMIT ? OFFSET ?",
            [limit, offset],
        ).fetchall()
    except duckdb.Error as e:
        raise HTTPException(500, f"Jadval sahifasini o'qib bo'lmadi: {str(e)[:200]}") from e
    finally:
        con.close()
    total = len(df)
    return {
        "columns": columns,
        "rows": [[None if pd.isna(value) else str(value) for value in row] for row in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(rows) < total,
    }


@app.post("/files/{file_id}/pivot")
def pivot_table(file_id: str, req: PivotRequest):
    item = get_item(file_id)
    df = typed_frame(item["versions"][-1]["df"])
    dimensions = req.rows + req.columns
    if not req.rows:
        raise HTTPException(400, "Kamida bitta qator guruhlash ustunini tanlang")
    if len(set(dimensions)) != len(dimensions):
        raise HTTPException(400, "Qator va ustun guruhlashlari takrorlanmasin")
    missing = [column for column in dimensions + [req.values] if column not in df.columns]
    if missing:
        raise HTTPException(400, f"Ustun topilmadi: {missing[0]}")
    if req.aggregation in {"sum", "mean", "min", "max"} and not pd.api.types.is_numeric_dtype(df[req.values]):
        raise HTTPException(400, "Tanlangan hisoblash usuli uchun qiymat ustuni raqamli bo'lishi kerak")
    try:
        if req.columns:
            result = pd.pivot_table(
                df,
                index=req.rows,
                columns=req.columns,
                values=req.values,
                aggfunc=req.aggregation,
                fill_value=0,
                margins=True,
                margins_name="Jami",
                dropna=False,
            ).reset_index()
            result.columns = [
                " / ".join(str(part) for part in column if str(part) != "")
                if isinstance(column, tuple) else str(column)
                for column in result.columns
            ]
        else:
            grouped = df.groupby(req.rows, dropna=False)[req.values].agg(req.aggregation).reset_index()
            total = df[req.values].agg(req.aggregation)
            total_row = {column: "" for column in grouped.columns}
            total_row[req.rows[0]] = "Jami"
            total_row[req.values] = total
            result = pd.concat([grouped, pd.DataFrame([total_row])], ignore_index=True)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"Pivot hisoblab bo'lmadi: {str(e)[:200]}") from e
    result = result.astype(object).where(result.notna(), None)
    return {
        "columns": [str(column) for column in result.columns],
        "rows": [[None if value is None else str(value) for value in row] for row in result.values.tolist()],
        "total_rows": len(result),
    }


@app.get("/files/{file_id}/report")
def report(file_id: str):
    item = get_item(file_id)
    df = item["versions"][-1]["df"]
    return {
        "file_id": file_id,
        "filename": item["filename"],
        "table": item["table"],
        **profile_dataframe(df),
        "preview": make_preview(df),
    }


@app.post("/files/{file_id}/clean")
def clean(file_id: str, req: CleanRequest):
    if not req.actions:
        raise HTTPException(400, "Kamida bitta tozalash amalini tanlang")
    item = get_item(file_id)
    return apply_cleaning(file_id, item, req.actions, req.dry_run)


@app.get("/recipes")
def list_recipes():
    folder = project_dir() / "recipes"
    if not folder.exists():
        return []
    recipes = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            recipes.append({"id": path.stem, "name": data["name"], "steps": len(data["actions"])})
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            raise HTTPException(500, f"Retsept faylini o'qib bo'lmadi ({path.name}): {e}") from e
    return recipes


@app.post("/recipes")
def create_recipe(req: RecipeIn):
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "Retsept nomini kiriting")
    if not req.actions:
        raise HTTPException(400, "Retseptga kamida bitta tozalash qadamini qo'shing")
    if len(req.actions) > 100:
        raise HTTPException(400, "Retsept 100 qadimgacha bo'lishi mumkin")
    folder = project_dir() / "recipes"
    recipe_id = uuid4().hex
    path = folder / f"{recipe_id}.json"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"name": name, "actions": [action.model_dump(exclude_none=True) for action in req.actions]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError as e:
        raise HTTPException(500, f"Retseptni saqlab bo'lmadi: {e}") from e
    return {"id": recipe_id, "name": name, "steps": len(req.actions)}


@app.post("/files/{file_id}/apply_recipe/{recipe_id}")
def apply_recipe(file_id: str, recipe_id: str, req: ApplyRecipeRequest):
    if not re.fullmatch(r"[0-9a-f]{32}", recipe_id):
        raise HTTPException(404, "Retsept topilmadi")
    path = project_dir() / "recipes" / f"{recipe_id}.json"
    if not path.is_file():
        raise HTTPException(404, "Retsept topilmadi")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        recipe = RecipeIn.model_validate(data)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        raise HTTPException(500, f"Retseptni o'qib bo'lmadi: {e}") from e
    if not recipe.actions:
        raise HTTPException(400, "Retseptda tozalash qadamlari yo'q")
    if len(recipe.actions) > 100:
        raise HTTPException(400, "Retsept 100 qadimgacha bo'lishi mumkin")
    item = get_item(file_id)
    return apply_cleaning(file_id, item, recipe.actions, req.dry_run, f"Retsept: {recipe.name}")


@app.post("/files/{file_id}/near_duplicates")
def find_near_duplicates(file_id: str, req: NearDuplicatesRequest):
    item = get_item(file_id)
    try:
        groups = near_duplicate_groups(item["versions"][-1]["df"], req.columns)
    except CleanError as e:
        raise HTTPException(400, str(e)) from e
    return {
        "columns": req.columns,
        "groups": groups,
        "duplicate_rows": sum(group["count"] - 1 for group in groups),
    }


@app.post("/files/{file_id}/undo")
def undo(file_id: str):
    item = get_item(file_id)
    if len(item["versions"]) <= 1:
        raise HTTPException(400, "Bekor qiladigan o'zgarish yo'q")
    undone = item["versions"].pop()
    (table_dir(file_id) / f"v{len(item['versions'])}.parquet").unlink(missing_ok=True)
    save_meta(file_id, item)
    df = item["versions"][-1]["df"]
    return {
        "undone": undone["label"],
        **profile_dataframe(df),
        "preview": make_preview(df),
    }


@app.get("/files/{file_id}/history")
def history(file_id: str):
    item = get_item(file_id)
    return {
        "versions": [
            {"step": i, "label": v["label"], "rows": len(v["df"])}
            for i, v in enumerate(item["versions"])
        ]
    }


def _safe_spreadsheet_value(value):
    if not isinstance(value, str):
        return value
    candidate = value.lstrip(" \t\r\n")
    if candidate.startswith(("=", "+", "-", "@")):
        try:
            float(candidate)
        except ValueError:
            return "'" + value
    return value


@app.get("/files/{file_id}/download")
def download(file_id: str):
    item = get_item(file_id)
    df = item["versions"][-1]["df"]
    data = df.map(_safe_spreadsheet_value).to_csv(index=False).encode("utf-8-sig")
    filename = f"{Path(item['filename']).stem}_cleaned.csv"
    filename = re.sub(r"[\r\n\"\\/]+", "_", filename)
    return Response(
        content=data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/files/{file_id}/stats")
def stats(file_id: str):
    item = get_item(file_id)
    try:
        return describe_dataframe(item["versions"][-1]["df"])
    except Exception as e:
        raise HTTPException(500, f"Statistika xatosi: {type(e).__name__}: {str(e)[:300]}")


@app.get("/files/{file_id}/summary")
def file_summary(file_id: str):
    item = get_item(file_id)
    try:
        return describe_dataframe(item["versions"][-1]["df"])
    except Exception as e:
        raise HTTPException(500, "Statistika xatosi: " + type(e).__name__ + ": " + str(e)[:300])


# ---------- AI va SQL ----------

@app.post("/files/{file_id}/ask")
def ask(file_id: str, req: AskRequest):
    item = get_item(file_id)
    df = item["versions"][-1]["df"]  # eng so'nggi (tozalangan) versiya
    try:
        check_query_budget(file_id)
        tables = {}
        for other_id in req.table_ids:
            if other_id == file_id:
                continue
            other = FILES.get(other_id)
            if other is not None:
                tables[other["table"]] = other["versions"][-1]["df"]
        tables["data"] = df
        history = recent_questions(file_id)
        result = ask_question(df, req.question, tables, file_id=file_id, history=history)
        record_recent_question(file_id, req.question)
        if req.explain and result.get("sql"):
            return explain_sql(result["sql"], tables)
        return result
    except SandboxUnavailableError as e:
        raise HTTPException(503, str(e)) from e
    except AIError as e:
        raise HTTPException(400, str(e))


@app.post("/sql")
def run_sql(req: SqlRequest):
    if not FILES:
        raise HTTPException(400, "Avval fayl yuklang")
    started = time.perf_counter()
    try:
        tables = {item["table"]: typed_frame(item["versions"][-1]["df"]) for item in FILES.values()}
        if req.active_id in FILES:  # faol jadval "data" nomi bilan ҳам mavjud
            tables["data"] = tables[FILES[req.active_id]["table"]]
        if req.explain:
            return explain_sql(req.sql, tables, req.error or None)
        sql = check_sql(req.sql)
        columns, rows, truncated = run_query_tables(tables, sql, SQL_MAX_ROWS)
    except SandboxUnavailableError as e:
        raise HTTPException(503, str(e)) from e
    except AIError as e:
        raise HTTPException(400, str(e))
    except duckdb.Error as e:
        raise HTTPException(400, f"SQL xatosi: {str(e)[:400]}")
    return {
        "columns": columns,
        "rows": rows,
        "truncated": truncated,
        "seconds": round(time.perf_counter() - started, 3),
    }


@app.post("/files/{file_id}/clean/suggest")
def suggest_cleaning(file_id: str):
    item = get_item(file_id)
    try:
        return suggest_cleaning_steps(item["versions"][-1]["df"])
    except AIError as e:
        raise HTTPException(400, str(e))


@app.post("/files/{file_id}/insights")
def insights(file_id: str, req: InsightRequest | None = None):
    item = get_item(file_id)
    try:
        limit = (req.limit if req else InsightRequest().limit)
        df = item["versions"][-1]["df"]
        return {"insights": generate_insights(df, {"data": df}, limit=limit)}
    except AIError as e:
        raise HTTPException(400, str(e))


from pycells import make_router as make_py_router  # noqa: E402

app.include_router(make_py_router(FILES, project_dir))

from extras import make_router as make_extras_router  # noqa: E402

app.include_router(
    make_extras_router(
        FILES,
        WORKSPACE,
        save_version,
        save_meta,
        make_table_name,
        project_dir,
        user_workspace_context,
        workspace_user_ids,
    )
)

from dashboard import make_router as make_dashboard_router  # noqa: E402

app.include_router(make_dashboard_router(FILES, project_dir))
