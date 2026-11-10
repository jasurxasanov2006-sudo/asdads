import os
import runpy
import sys
import threading
import time
import webbrowser
from pathlib import Path


def main():
    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    backend = bundle / "backend"
    sys.path.insert(0, str(backend))
    if len(sys.argv) > 2 and sys.argv[1] == "--dataflow-kernel":
        worker = Path(sys.argv[2])
        sys.argv = [str(worker), "--kernel"]
        runpy.run_path(str(worker), run_name="__main__")
        return

    data_dir = Path(os.getenv("APPDATA", Path.home())) / "DataFlowAI"
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DATAFLOW_DATA_DIR", str(data_dir))
    os.environ.setdefault("DATAFLOW_AI_ENV_FILE", str(data_dir / ".env"))
    os.environ.setdefault("DATAFLOW_AUTH_ENABLED", "true")
    os.environ.setdefault("DATAFLOW_PYTHON_SANDBOX", "local")

    import uvicorn

    port = int(os.getenv("DATAFLOW_PORT", "8000"))
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(
        "main:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
    ))
    thread = threading.Thread(target=server.run, name="dataflow-server", daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while thread.is_alive() and not server.started and time.monotonic() < deadline:
        time.sleep(0.1)
    if server.started:
        webbrowser.open(url)
    else:
        server.should_exit = True
        thread.join(timeout=3)
        raise RuntimeError("DataFlow AI serveri ishga tushmadi. Port va terminaldagi xabarni tekshiring.")
    thread.join()


if __name__ == "__main__":
    main()
