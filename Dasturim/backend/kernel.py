import ctypes
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


KERNEL_TIMEOUT = 30
KERNEL_MEMORY_LIMIT = 1024 * 1024 * 1024


if os.name == "nt":
    from ctypes import wintypes

    class _BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


def _assign_windows_job(process: subprocess.Popen) -> int | None:
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD
    ]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "Windows Job Object yaratilmadi")
    info = _ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = 0x00000100 | 0x00000008 | 0x00002000
    # Windows venv launchers can keep a runtime child beside the worker launcher.
    info.BasicLimitInformation.ActiveProcessLimit = 2
    info.ProcessMemoryLimit = KERNEL_MEMORY_LIMIT
    if not kernel32.SetInformationJobObject(
        job, 9, ctypes.byref(info), ctypes.sizeof(info)
    ):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(job)
        raise OSError(error, "Notebook xotira limitini o'rnatib bo'lmadi")
    if not kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(process._handle)):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(job)
        raise OSError(error, "Notebook worker'ini Windows Job Object'ga biriktirib bo'lmadi")
    return job


class NotebookKernel:
    def __init__(self, worker_path: Path):
        self.worker_path = worker_path
        self.process: subprocess.Popen | None = None
        self.job = None
        self.stderr_file = None
        self.lock = threading.Lock()
        self.timed_out = False

    def _start(self) -> None:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "WINDIR": os.environ.get("WINDIR", ""),
            "TEMP": os.environ.get("TEMP", ""),
            "TMP": os.environ.get("TMP", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        self.stderr_file = tempfile.TemporaryFile()
        command = (
            [sys.executable, "--dataflow-kernel", str(self.worker_path)]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-u", str(self.worker_path), "--kernel"]
        )
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.stderr_file,
                text=True,
                encoding="utf-8",
                cwd=str(self.worker_path.parent),
                env=env,
                bufsize=1,
            )
        except OSError:
            self.stderr_file.close()
            self.stderr_file = None
            raise
        try:
            self.job = _assign_windows_job(process)
        except OSError:
            process.kill()
            process.wait()
            self.stderr_file.close()
            self.stderr_file = None
            raise
        self.process = process

    def _read_stderr(self) -> str:
        if not self.stderr_file:
            return ""
        self.stderr_file.flush()
        self.stderr_file.seek(0, os.SEEK_END)
        end = self.stderr_file.tell()
        self.stderr_file.seek(max(0, end - 2000))
        return self.stderr_file.read().decode("utf-8", errors="replace").strip()

    def _stop(self) -> None:
        process, self.process = self.process, None
        if process:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
        if self.job and os.name == "nt":
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self.job)
        self.job = None
        if self.stderr_file:
            self.stderr_file.close()
            self.stderr_file = None

    def interrupt(self) -> bool:
        process = self.process
        if not process or process.poll() is not None:
            return False
        process.kill()
        return True

    def restart(self) -> None:
        with self.lock:
            self._stop()
            self.timed_out = False

    def close(self) -> None:
        with self.lock:
            self._stop()

    def run(self, payload_path: Path) -> dict:
        with self.lock:
            if not self.process or self.process.poll() is not None:
                self._stop()
                self._start()
            process = self.process
            if not process or not process.stdin or not process.stdout:
                raise RuntimeError("Notebook kernel ishga tushmadi")

            self.timed_out = False

            def terminate_for_timeout() -> None:
                self.timed_out = True
                self.interrupt()

            timer = threading.Timer(KERNEL_TIMEOUT, terminate_for_timeout)
            timer.daemon = True
            timer.start()
            try:
                process.stdin.write(json.dumps({"payload": str(payload_path)}) + "\n")
                process.stdin.flush()
                response = process.stdout.readline()
            except (BrokenPipeError, OSError) as e:
                details = self._read_stderr()
                self._stop()
                message = "Notebook kernel to'xtab qoldi va qayta ishga tushirildi"
                if details:
                    message += f": {details}"
                raise RuntimeError(message) from e
            finally:
                timer.cancel()

            if self.timed_out:
                self._stop()
                raise TimeoutError(f"Kod {KERNEL_TIMEOUT} soniyadan ko'p ishladi va to'xtatildi")
            if not response:
                details = self._read_stderr()
                code = process.poll()
                self._stop()
                message = f"Notebook kernel javob bermadi va to'xtadi (jarayon kodi: {code})"
                if details:
                    message += f": {details}"
                raise RuntimeError(message)
            try:
                result = json.loads(response)
            except json.JSONDecodeError as e:
                self._stop()
                raise RuntimeError("Notebook kernel javobini o'qib bo'lmadi") from e
            if process.poll() is not None:
                self._stop()
            return result
