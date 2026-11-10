import atexit
import json
import os
import pickle
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from ai import ENV_FILE, AIError, call_model, explain_python, schema_text, typed_frame
from kernel import KERNEL_TIMEOUT, NotebookKernel
from security import auth_enabled

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
JS_FILE = ROOT / "frontend" / "pycells.js"
RUNNER = HERE / "pyrunner.py"
NOTEBOOK = ROOT / "workspace" / "notebook.json"
TIMEOUT = KERNEL_TIMEOUT
MAX_CODE = 20000
MAX_CELLS = 100
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
KERNELS: dict[str, NotebookKernel] = {}
KERNELS_LOCK = threading.Lock()
MAX_NOTEBOOK_BYTES = 2 * 1024 * 1024

SYSTEM = """Sen pandas mutaxassisisan. Foydalanuvchi Python kataklarida data tahlil qiladi.
Mavjud o'zgaruvchilar: df (faol jadval, pandas DataFrame; raqam va sana ustunlari tegishli turda), tables (dict: jadval nomi -> DataFrame), pd, np.
Qoidalar:
- pandas va numpy ishlat; grafik uchun matplotlib, ML uchun o'rnatilgan scikit-learn'dan foydalanish mumkin.
- Fayl, tarmoq, os, subprocess bilan ishlama. Xavfsiz kod siyosati ayrim amallarni bloklaydi.
- Natijani oxirgi qatorda ifoda sifatida qaytar (DataFrame yoki qiymat) yoki print qil.
- Ustun nomlarini faqat berilganlaridan ol; kod qisqa va tushunarli bo'lsin, izohlar o'zbekcha.
- Javobni FAQAT JSON qilib ber: {"code": "...", "explanation": "..."}.
- "explanation": o'zbekcha 1-3 gap. Xatoni tuzatishda: xato sababi nima va nimani o'zgartirding."""


class RunRequest(BaseModel):
    code: str
    before: list[str] = Field(default_factory=list)
    active_id: str | None = None
    execution_id: str | None = None


class InterruptRequest(BaseModel):
    execution_id: str


class CellIn(BaseModel):
    id: str
    code: str
    type: str = "code"


class NotebookIn(BaseModel):
    cells: list[CellIn]


class AiRequest(BaseModel):
    task: str  # "write", "fix" yoki "explain"
    prompt: str = ""
    code: str = ""
    error: str = ""
    active_id: str | None = None


def guard(request: Request) -> None:
    """Local Python is localhost-only; deployed Python requires the isolated sandbox."""
    mode = os.getenv("DATAFLOW_PYTHON_SANDBOX", "local").strip().lower()
    if request.headers.get("x-dataflow") != "1":
        raise HTTPException(403, "So'rov manbai noto'g'ri")
    if mode == "docker":
        if not auth_enabled():
            raise HTTPException(503, "Sandbox rejimida foydalanuvchi autentifikatsiyasi majburiy")
        return
    if mode != "local":
        raise HTTPException(503, "Python sandbox rejimi noto'g'ri sozlangan")
    client = request.client.host if request.client else ""
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
    if client not in LOCAL_HOSTS or host not in LOCAL_HOSTS:
        raise HTTPException(403, "Python kodi faqat shu kompyuterning o'zida (127.0.0.1) bajariladi")
    origin = request.headers.get("origin")
    if origin:
        origin_host = origin.split("://", 1)[-1].rsplit(":", 1)[0].strip("[]")
        if origin_host not in LOCAL_HOSTS:
            raise HTTPException(403, "So'rov manbai ruxsat etilmagan")


def run_in_sandbox(df, frames, req: RunRequest, execution_id: str) -> dict:
    endpoint = os.getenv("DATAFLOW_PYTHON_SANDBOX_URL", "").strip()
    sandbox_token = os.getenv("DATAFLOW_SANDBOX_TOKEN", "")
    if not endpoint or len(sandbox_token) < 32:
        raise HTTPException(503, "Izolyatsiyalangan Python sandbox sozlamasi to'liq emas")
    if len(req.before) > MAX_CELLS - 1 or any(len(code) > MAX_CODE for code in req.before):
        raise HTTPException(400, "Oldingi kataklarning soni yoki kodi ruxsat etilgan hajmdan oshdi")
    tables = {}
    active_name = None
    for name, frame in frames.items():
        serialized = json.loads(frame.to_json(orient="split", date_format="iso", default_handler=str))
        tables[name] = {"columns": serialized["columns"], "rows": serialized["data"]}
        if frame is df:
            active_name = name
    if active_name is None:
        raise HTTPException(400, "Faol jadval topilmadi")
    body = json.dumps({
        "execution_id": execution_id,
        "frames": tables,
        "active": active_name,
        "codes": req.before + [req.code],
    }, ensure_ascii=False).encode("utf-8")
    if len(body) > 256 * 1024 * 1024:
        raise HTTPException(413, "Python sandbox uchun jadval ma'lumotlari 256 MB dan katta")
    sandbox_request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {sandbox_token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(sandbox_request, timeout=40) as response:
            return json.loads(response.read(16 * 1024 * 1024 + 1))
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read(4096)).get("detail", "Sandbox xatosi")
        except (ValueError, AttributeError):
            detail = "Sandbox xatosi"
        raise HTTPException(error.code, detail) from error
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise HTTPException(503, f"Python sandbox bilan bog'lanib bo'lmadi: {str(error)[:200]}") from error


def parse_json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise AIError("AI javobini o'qib bo'lmadi. Qayta urinib ko'ring")
        try:
            data = json.loads(match.group(0))
        except ValueError:
            raise AIError("AI javobini o'qib bo'lmadi. Qayta urinib ko'ring")
    if not isinstance(data, dict):
        raise AIError("AI javobini o'qib bo'lmadi. Qayta urinib ko'ring")
    return str(data.get("code", "")).strip("\n"), str(data.get("explanation", "")).strip()


def get_kernel(path: Path) -> NotebookKernel:
    key = str(path.resolve())
    with KERNELS_LOCK:
        if key not in KERNELS:
            KERNELS[key] = NotebookKernel(RUNNER)
        return KERNELS[key]


def close_kernels() -> None:
    with KERNELS_LOCK:
        for kernel in KERNELS.values():
            kernel.close()


atexit.register(close_kernels)


def make_router(files: dict, workspace: Path | Callable[[], Path] | None = None) -> APIRouter:
    router = APIRouter()

    def notebook_path() -> Path:
        if callable(workspace):
            return workspace() / "notebook.json"
        if isinstance(workspace, Path):
            return workspace / "notebook.json"
        return NOTEBOOK

    def build_frames(active_id):
        if not files:
            raise HTTPException(400, "Avval fayl yuklang")
        frames = {f["table"]: typed_frame(f["versions"][-1]["df"]) for f in files.values()}
        active = files.get(active_id) if active_id else None
        df = frames[active["table"]] if active else next(iter(frames.values()))
        return df, frames

    @router.get("/pycells.js", include_in_schema=False)
    def pycells_js():
        if not JS_FILE.is_file():
            raise HTTPException(404, f"Fayl topilmadi: {JS_FILE}")
        return FileResponse(JS_FILE, media_type="application/javascript")

    def load_notebook():
        path = notebook_path()
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise HTTPException(500, f"Daftarni o'qib bo'lmadi: {e}")
            if not isinstance(data, list):
                raise HTTPException(500, "Daftar formati noto'g'ri")
            result = []
            for cell in data:
                if not isinstance(cell, dict):
                    continue
                entry = {
                    "id": str(cell.get("id", "c")),
                    "code": str(cell.get("code", "")),
                }
                if cell.get("type") == "markdown":
                    entry["type"] = "markdown"
                result.append(entry)
            return result
        return []

    @router.get("/py/notebook")
    def get_notebook(request: Request):
        guard(request)
        return load_notebook()

    @router.post("/py/notebook")
    def save_notebook(nb: NotebookIn, request: Request):
        guard(request)
        if len(nb.cells) > MAX_CELLS:
            raise HTTPException(400, f"Daftarda ko'pi bilan {MAX_CELLS} ta katak bo'lishi mumkin")
        cells = []
        for cell in nb.cells:
            if cell.type not in ("code", "markdown"):
                raise HTTPException(400, "Katak turi code yoki markdown bo'lishi kerak")
            if len(cell.code) > MAX_CODE:
                raise HTTPException(400, "Katak kodi juda uzun")
            cells.append({
                "id": re.sub(r"[^0-9a-zA-Z_-]", "", cell.id)[:32] or "c",
                "type": cell.type,
                "code": cell.code,
            })
        path = notebook_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")
        return {"saved": len(cells)}

    @router.post("/py/run")
    def run_cell(req: RunRequest, request: Request):
        guard(request)
        if len(req.code) > MAX_CODE:
            raise HTTPException(400, "Kod juda uzun")
        if len(req.before) > MAX_CELLS - 1 or any(len(code) > MAX_CODE for code in req.before):
            raise HTTPException(400, "Oldingi kataklarning soni yoki kodi ruxsat etilgan hajmdan oshdi")
        df, frames = build_frames(req.active_id)
        started = time.perf_counter()
        if os.getenv("DATAFLOW_PYTHON_SANDBOX", "local").strip().lower() == "docker":
            execution_id = req.execution_id or uuid4().hex
            if not re.fullmatch(r"[a-f0-9]{32}", execution_id):
                raise HTTPException(400, "Bajarish identifikatori noto'g'ri")
            data = run_in_sandbox(df, frames, req, execution_id)
            data["seconds"] = round(time.perf_counter() - started, 3)
            return data
        with tempfile.NamedTemporaryFile(prefix="dataflow-", suffix=".pkl", delete=False) as fh:
            work = Path(fh.name)
            pickle.dump({"code": req.code, "df": df, "tables": frames}, fh)
        try:
            data = get_kernel(notebook_path()).run(work)
        except TimeoutError as e:
            raise HTTPException(408, str(e))
        except (OSError, RuntimeError) as e:
            raise HTTPException(500, str(e))
        finally:
            work.unlink(missing_ok=True)
        data["seconds"] = round(time.perf_counter() - started, 3)
        return data

    @router.get("/py/mode")
    def python_mode(request: Request):
        guard(request)
        return {"mode": os.getenv("DATAFLOW_PYTHON_SANDBOX", "local").strip().lower()}

    @router.post("/py/interrupt")
    def interrupt_kernel(req: InterruptRequest, request: Request):
        guard(request)
        if os.getenv("DATAFLOW_PYTHON_SANDBOX", "local").strip().lower() == "docker":
            endpoint = os.getenv("DATAFLOW_PYTHON_SANDBOX_URL", "").strip()
            sandbox_token = os.getenv("DATAFLOW_SANDBOX_TOKEN", "")
            if not endpoint or len(sandbox_token) < 32:
                raise HTTPException(503, "Izolyatsiyalangan Python sandbox sozlamasi to'liq emas")
            if not re.fullmatch(r"[a-f0-9]{32}", req.execution_id):
                raise HTTPException(400, "Bajarish identifikatori noto'g'ri")
            interrupt_request = urllib.request.Request(
                endpoint.rsplit("/", 1)[0] + "/interrupt",
                data=json.dumps({"execution_id": req.execution_id}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {sandbox_token}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(interrupt_request, timeout=6) as response:
                    return json.loads(response.read(4096))
            except urllib.error.HTTPError as error:
                raise HTTPException(error.code, "Python sandbox bajarishni to'xtata olmadi") from error
            except urllib.error.URLError as error:
                raise HTTPException(503, f"Python sandbox bilan bog'lanib bo'lmadi: {error.reason}") from error
        kernel = KERNELS.get(str(notebook_path().resolve()))
        return {"interrupted": kernel.interrupt() if kernel else False}

    @router.post("/py/restart")
    def restart_kernel(request: Request):
        guard(request)
        if os.getenv("DATAFLOW_PYTHON_SANDBOX", "local").strip().lower() == "docker":
            return {"restarted": True, "mode": "isolated"}
        get_kernel(notebook_path()).restart()
        return {"restarted": True}

    @router.get("/py/export.py")
    def export_py(request: Request):
        guard(request)
        cells = load_notebook()
        text = "\n\n".join(
            (
                "\n".join(f"# {line}" if line else "#" for line in cell["code"].splitlines())
                if cell.get("type", "code") == "markdown" else cell["code"]
            )
            for cell in cells
        )
        return Response(
            text, media_type="text/x-python; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="notebook.py"'},
        )

    @router.get("/py/export.ipynb")
    def export_ipynb(request: Request):
        guard(request)
        cells = load_notebook()
        notebook = {
            "cells": [
                {
                    "cell_type": cell.get("type", "code"),
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": cell["code"].splitlines(keepends=True),
                }
                for cell in cells
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3", "language": "python", "name": "python3"
                },
                "language_info": {"name": "python", "version": "3"},
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        return Response(
            json.dumps(notebook, ensure_ascii=False, indent=1),
            media_type="application/x-ipynb+json",
            headers={"Content-Disposition": 'attachment; filename="notebook.ipynb"'},
        )

    @router.post("/py/import")
    async def import_notebook(request: Request, file: UploadFile = File(...)):
        guard(request)
        name = (file.filename or "").lower()
        if not name.endswith((".py", ".ipynb")):
            raise HTTPException(400, "Faqat .py yoki .ipynb faylini import qilish mumkin")
        raw = await file.read(MAX_NOTEBOOK_BYTES + 1)
        if len(raw) > MAX_NOTEBOOK_BYTES:
            raise HTTPException(413, "Daftar fayli 2 MB dan kichik bo'lishi kerak")
        try:
            text = raw.decode("utf-8-sig")
            if name.endswith(".py"):
                cells = [{"id": "imported", "type": "code", "code": text}]
            else:
                notebook = json.loads(text)
                if notebook.get("nbformat") != 4 or not isinstance(notebook.get("cells"), list):
                    raise ValueError("Jupyter daftar formati qo'llab-quvvatlanmaydi")
                if len(notebook["cells"]) > MAX_CELLS:
                    raise ValueError(f"Daftarda ko'pi bilan {MAX_CELLS} ta katak bo'lishi mumkin")
                cells = []
                for index, cell in enumerate(notebook["cells"]):
                    kind = cell.get("cell_type")
                    if kind not in ("code", "markdown"):
                        continue
                    source = cell.get("source", "")
                    code = "".join(source) if isinstance(source, list) else str(source)
                    if len(code) > MAX_CODE:
                        raise ValueError(f"{index + 1}-katak juda uzun")
                    cells.append({"id": f"imported-{index}", "type": kind, "code": code})
        except (UnicodeDecodeError, ValueError, TypeError, AttributeError) as e:
            raise HTTPException(400, f"Daftar faylini o'qib bo'lmadi: {e}")
        if any(len(cell["code"]) > MAX_CODE for cell in cells):
            raise HTTPException(400, "Katak kodi 20 000 belgidan uzun bo'lishi mumkin emas")
        path = notebook_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cells, ensure_ascii=False), encoding="utf-8")
        return {"cells": cells}

    @router.post("/py/ai")
    def py_ai(req: AiRequest, request: Request):
        guard(request)
        load_dotenv(ENV_FILE, override=True)
        df, _ = build_frames(req.active_id)
        send_sample = os.getenv("AI_SEND_SAMPLE", "true").strip().lower() != "false"
        schema = schema_text(df, send_sample)
        if req.task == "fix":
            user = (
                f"df ustunlari:\n{schema}\n\nMen yozgan kod:\n{req.code[:6000]}\n\n"
                f"Chiqqan xato:\n{req.error[:2000]}\n\n"
                "Xato sababini tushuntir va tuzatilgan to'liq kodni ber."
            )
        elif req.task == "explain":
            code = (req.code or "").strip()
            if not code:
                raise HTTPException(400, "Tushuntirish kerak bo'lgan kodni kiriting")
            try:
                result = explain_python(code, req.error or None)
                return {"code": result["code"], "explanation": result["explanation"]}
            except AIError as e:
                raise HTTPException(400, str(e))
        else:
            if not req.prompt.strip():
                raise HTTPException(400, "Nima qilish kerakligini yozing")
            user = f"df ustunlari:\n{schema}\n\nVazifa: {req.prompt.strip()[:500]}"
        try:
            code, explanation = parse_json(call_model(SYSTEM, user))
        except AIError as e:
            raise HTTPException(400, str(e))
        if not code:
            raise HTTPException(400, explanation or "AI kod yozmadi")
        return {"code": code, "explanation": explanation}

    return router