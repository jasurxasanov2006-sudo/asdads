import json
import hmac
import os
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_REQUEST = 256 * 1024 * 1024
MAX_RESPONSE = 16 * 1024 * 1024
TIMEOUT_SECONDS = 30
IMAGE = os.environ.get("SANDBOX_IMAGE", "dataflow-python-sandbox:latest")
SANDBOX_TOKEN = os.environ.get("DATAFLOW_SANDBOX_TOKEN", "")
active = {}
active_lock = threading.Lock()
run_slots = threading.BoundedSemaphore(2)


def prepare_image():
    subprocess.run(
        ["docker", "build", "--quiet", "-t", IMAGE, "/sandbox-image"],
        check=True,
        timeout=300,
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "DataFlowSandbox/1"

    def log_message(self, format_string, *args):
        print(format_string % args, flush=True)

    def send_json(self, status, value):
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_payload(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Content-Length noto'g'ri")
        if length <= 0 or length > MAX_REQUEST:
            raise ValueError("Sandbox so'rovi hajmi ruxsat etilgan chegaradan oshdi")
        body = self.rfile.read(length)
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("Sandbox so'rovi formati noto'g'ri")
        execution_id = payload.get("execution_id")
        if not isinstance(execution_id, str) or not re.fullmatch(r"[a-f0-9]{32}", execution_id):
            raise ValueError("Bajarish identifikatori noto'g'ri")
        if not isinstance(payload.get("frames"), dict) or len(payload["frames"]) > 100:
            raise ValueError("Sandbox jadval soni ruxsat etilgan chegaradan oshdi")
        if payload.get("kind", "python") == "python":
            codes = payload.get("codes")
            if not isinstance(codes, list) or not codes or len(codes) > 100:
                raise ValueError("Notebook kataklari soni noto'g'ri")
            if any(not isinstance(code, str) or len(code) > 20_000 for code in codes):
                raise ValueError("Python katak kodi hajmi ruxsat etilgan chegaradan oshdi")
        elif payload["kind"] == "sql":
            if not isinstance(payload.get("sql"), str) or len(payload["sql"]) > 20_000:
                raise ValueError("SQL so'rovi noto'g'ri yoki juda uzun")
            if not isinstance(payload.get("limit"), int) or not 1 <= payload["limit"] <= 1000:
                raise ValueError("SQL natija limiti noto'g'ri")
        else:
            raise ValueError("Sandbox vazifasi turi noto'g'ri")
        return body, execution_id

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok"})
            return
        self.send_json(404, {"detail": "Topilmadi"})

    def do_POST(self):
        authorization = self.headers.get("Authorization", "")
        if len(SANDBOX_TOKEN) < 32 or not hmac.compare_digest(
            authorization, f"Bearer {SANDBOX_TOKEN}"
        ):
            self.send_json(401, {"detail": "Sandbox autentifikatsiyasi xato"})
            return
        if self.path == "/run":
            self.run_code()
        elif self.path == "/interrupt":
            self.interrupt()
        else:
            self.send_json(404, {"detail": "Topilmadi"})

    def run_code(self):
        if not run_slots.acquire(blocking=False):
            self.send_json(429, {"detail": "Sandbox band. Birozdan keyin qayta urinib ko'ring."})
            return
        try:
            body, execution_id = self.read_payload()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json(400, {"detail": str(error)})
            run_slots.release()
            return

        container_name = f"dataflow-sandbox-{execution_id}"
        command = [
            "docker", "run", "--rm", "--interactive", "--name", container_name,
            "--network=none", "--memory=1g", "--memory-swap=1g", "--cpus=1",
            "--pids-limit=32", "--read-only", "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=32m",
            "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
            "--user=65534:65534", "--ulimit=nofile=64:64", "--log-driver=none",
            IMAGE,
        ]
        try:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as error:
            self.send_json(503, {"detail": f"Sandbox konteynerini ishga tushirib bo'lmadi: {error}"})
            run_slots.release()
            return
        with active_lock:
            active[execution_id] = (process, container_name)
        try:
            stdout, stderr = process.communicate(body, timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            self.stop_container(process, container_name)
            self.send_json(408, {"detail": "Python kodi 30 soniyalik vaqt limitidan oshdi"})
            return
        finally:
            with active_lock:
                active.pop(execution_id, None)
            run_slots.release()

        if process.returncode != 0:
            print(f"Sandbox worker failed ({execution_id}): {stderr.decode('utf-8', 'replace')[:1000]}", flush=True)
            self.send_json(503, {"detail": "Sandbox konteynerida kod bajarilmadi"})
            return
        if len(stdout) > MAX_RESPONSE:
            self.send_json(502, {"detail": "Sandbox javobi ruxsat etilgan hajmdan katta"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(stdout)))
        self.end_headers()
        self.wfile.write(stdout)

    @staticmethod
    def stop_container(process, container_name):
        try:
            subprocess.run(
                ["docker", "stop", "--time", "1", container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=4,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass
        if process.poll() is None:
            process.kill()

    def interrupt(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1024:
                raise ValueError("So'rov hajmi noto'g'ri")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("So'rov formati noto'g'ri")
            execution_id = payload.get("execution_id")
        except (ValueError, json.JSONDecodeError):
            self.send_json(400, {"detail": "Bajarish identifikatori noto'g'ri"})
            return
        if not isinstance(execution_id, str) or not re.fullmatch(r"[a-f0-9]{32}", execution_id):
            self.send_json(400, {"detail": "Bajarish identifikatori noto'g'ri"})
            return
        with active_lock:
            entry = active.get(execution_id)
        if not entry:
            self.send_json(200, {"interrupted": False})
            return
        self.stop_container(*entry)
        self.send_json(200, {"interrupted": True})


if len(SANDBOX_TOKEN) < 32:
    raise RuntimeError("DATAFLOW_SANDBOX_TOKEN 32 belgidan uzun bo'lishi shart")
prepare_image()
server = ThreadingHTTPServer(("0.0.0.0", 8787), Handler)
server.daemon_threads = True
server.serve_forever()
