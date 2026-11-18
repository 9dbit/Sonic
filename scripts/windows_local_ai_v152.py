"""Windows-only local GGUF manager for the SONIC Limited-user Companion.

Fixed paths/arguments, loopback-only HTTP, explicit owner-signed remote jobs.
No autonomous startup, shell=True, public ports, trading access or model tools.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(r"E:\AI\DeepSeek-V4-Pro-Qwen3.5-9B")
EXE = ROOT / "runtime" / "vulkan" / "llama-server.exe"
MODEL = ROOT / "model" / "DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic.Q4_K_M.gguf"
RECEIPT = ROOT / "model-verified.sha256"
OPT_IN = ROOT / "allow-sonic-local-ai.flag"
LOCAL = "http://127.0.0.1:11435"
EXPECTED_HASH = "b4363b5710a29a03cab49bc10df92ca688f891eba1a63cae912e4d96f3fd7a65"
EXPECTED_SIZE = 5780092768
MAX_OUTPUT = 4000


def is_enabled() -> bool:
    try:
        return OPT_IN.read_text(encoding="utf-8").strip() == "SONIC_LOCAL_AI_OWNER_APPROVED_V152"
    except OSError:
        return False


def memory_free_mb() -> int:
    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    ("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong),
                    ("swap_total", ctypes.c_ulonglong), ("swap_free", ctypes.c_ulonglong),
                    ("virtual_total", ctypes.c_ulonglong), ("virtual_free", ctypes.c_ulonglong),
                    ("extended", ctypes.c_ulonglong)]
    info = Memory()
    info.length = ctypes.sizeof(info)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
        raise RuntimeError("RAM_METRICS_UNAVAILABLE")
    return int(info.free // (1024 * 1024))


def gpu_memory():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free,memory.used", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            timeout=4, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        first = result.stdout.splitlines()[0].split(",")
        return int(first[0].strip()), int(first[1].strip())
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None, None


def server_ready() -> bool:
    try:
        with urlopen(LOCAL + "/health", timeout=1.5) as response:
            return response.status == 200 and response.read(256).find(b'"ok"') >= 0
    except (OSError, TimeoutError, ValueError):
        return False


def model_verified() -> bool:
    try:
        return (
            EXE.is_file() and MODEL.is_file() and MODEL.stat().st_size == EXPECTED_SIZE
            and not Path(str(MODEL) + ".aria2").exists()
            and RECEIPT.is_file()
            and RECEIPT.read_text(encoding="ascii").lower().startswith(EXPECTED_HASH)
        )
    except OSError:
        return False


class LocalAIBroker:
    def __init__(self):
        self._process = None
        self._log = None
        self._lock = threading.RLock()
        self._worker = None
        self._pending_receipt = None

    def status(self) -> dict:
        free = memory_free_mb()
        gpu_free, gpu_used = gpu_memory()
        running = server_ready()
        with self._lock:
            starting = bool(self._process and self._process.poll() is None and not running)
        return {"state": "running" if running else "starting" if starting else "stopped" if model_verified() else "unavailable",
                "ram_free_mb": free, "gpu_free_mb": gpu_free, "gpu_used_mb": gpu_used}

    def start(self) -> dict:
        if not is_enabled() or not model_verified():
            raise PermissionError("LOCAL_MODEL_NOT_OWNER_APPROVED_OR_VERIFIED")
        with self._lock:
            if server_ready():
                return {"state": "running", "detail": "already_available"}
            if self._process and self._process.poll() is None:
                return {"state": "starting"}
            if memory_free_mb() < 6500:
                raise RuntimeError("RAM_GUARD_MIN_6500MB")
            vram, _ = gpu_memory()
            if vram is None or vram < 2700:
                raise RuntimeError("GPU_GUARD_MIN_2700MB")
            log_path = ROOT / "logs" / "sonic-local-ai.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            if log_path.exists() and log_path.stat().st_size > 2 * 1024 * 1024:
                log_path.replace(log_path.with_suffix(".previous.log"))
            self._log = log_path.open("ab")
            args = [str(EXE), "--model", str(MODEL), "--host", "127.0.0.1",
                    "--port", "11435", "--ctx-size", "1024", "--n-gpu-layers", "12",
                    "--threads", "2", "--parallel", "1", "--batch-size", "128",
                    "--ubatch-size", "128"]
            flags = (getattr(subprocess, "CREATE_NO_WINDOW", 0) |
                     getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
            self._process = subprocess.Popen(args, cwd=str(EXE.parent), shell=False,
                                             stdout=self._log, stderr=subprocess.STDOUT,
                                             creationflags=flags)
            return {"state": "starting"}

    def stop(self) -> dict:
        with self._lock:
            proc = self._process
            if proc is None or proc.poll() is not None:
                if server_ready():
                    raise PermissionError("AI_SERVER_NOT_OWNED_BY_SONIC_COMPANION")
                return {"state": "stopped"}
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                # Do not kill an arbitrary process or terminate MT5.
                raise RuntimeError("LOCAL_AI_STOP_TIMED_OUT")
            self._process = None
            if self._log:
                self._log.close()
                self._log = None
            return {"state": "stopped"}

    def chat(self, payload: dict) -> dict:
        if not is_enabled() or not server_ready():
            raise RuntimeError("LOCAL_AI_NOT_RUNNING")
        messages = payload.get("messages") if isinstance(payload, dict) else None
        if not isinstance(messages, list) or not 2 <= len(messages) <= 6:
            raise ValueError("UNEXPECTED_CHAT_MESSAGES")
        if any(not isinstance(item, dict) or set(item) != {"role", "content"} or
               item["role"] not in ("system", "user", "assistant") or
               not isinstance(item["content"], str) or len(item["content"]) > 1500
               for item in messages):
            raise ValueError("INVALID_CHAT_MESSAGE")
        if messages[-1]["role"] != "user":
            raise ValueError("LAST_MESSAGE_MUST_BE_USER")
        code_draft = payload.get("task") == "code"
        if payload.get("task") not in (None, "code"):
            raise ValueError("INVALID_LOCAL_TASK")
        local_messages = [dict(item) for item in messages]
        local_messages[-1]["content"] = "/no_think " + local_messages[-1]["content"]
        body = json.dumps({
            "messages": local_messages, "temperature": 0, "max_tokens": 384 if code_draft else 256,
            "stream": False, "chat_template_kwargs": {"enable_thinking": False}
        }, ensure_ascii=False).encode("utf-8")
        if len(body) > 5400:
            raise ValueError("LOCAL_CONTEXT_TOO_LONG")
        req = Request(LOCAL + "/v1/chat/completions", data=body, method="POST",
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=125 if code_draft else 75) as response:
            if response.status != 200:
                raise RuntimeError("LOCAL_INFERENCE_REJECTED")
            raw = response.read(16384)
        data = json.loads(raw)
        choice = data["choices"][0]
        content = choice["message"]["content"]
        if choice.get("finish_reason") not in ("stop", "length") or not isinstance(content, str) or not content.strip():
            raise RuntimeError("LOCAL_INFERENCE_EMPTY")
        if code_draft and choice.get("finish_reason") != "stop":
            raise RuntimeError("LOCAL_CODE_OUTPUT_TRUNCATED")
        usage = data.get("usage", {})
        return {"text": content[:MAX_OUTPUT], "truncated": choice.get("finish_reason") == "length",
                "usage": {"input_tokens": usage.get("prompt_tokens"),
                          "output_tokens": usage.get("completion_tokens")}}

    def dispatch(self, api, device_id):
        """Called in Companion's 8s loop; executes one operation on a worker thread."""
        if not is_enabled():
            return
        api("/api/device/local-ai/heartbeat", {"device_id": device_id, **self.status()})
        with self._lock:
            pending = self._pending_receipt
            busy = bool(self._worker and self._worker.is_alive())
        if pending is not None:
            api("/api/device/local-ai/result", pending)
            with self._lock:
                if self._pending_receipt is pending:
                    self._pending_receipt = None
            return
        if busy:
            return
        item = api("/api/device/local-ai/next", {}).get("job")
        if not item:
            return
        if not isinstance(item, dict) or item.get("action") not in ("chat", "code", "start", "stop"):
            return
        def run():
            try:
                action = item["action"]
                result = self.chat(item.get("payload", {})) if action in ("chat", "code") else (
                    self.start() if action == "start" else self.stop())
                receipt = {"device_id": device_id, "job_id": item["id"],
                           "success": True, "result": result}
            except Exception as exc:
                # Return a bounded diagnostic code only, not prompts, paths or exceptions.
                if isinstance(exc, TimeoutError):
                    code = "LOCAL_INFERENCE_TIMEOUT"
                elif isinstance(exc, HTTPError):
                    code = "LOCAL_INFERENCE_REJECTED"
                elif isinstance(exc, URLError):
                    code = "LOCAL_MODEL_NOT_RUNNING"
                elif isinstance(exc, RuntimeError) and str(exc) in {
                    "LOCAL_INFERENCE_EMPTY", "LOCAL_CODE_OUTPUT_TRUNCATED",
                    "LOCAL_AI_NOT_RUNNING", "LOCAL_INFERENCE_REJECTED"}:
                    code = str(exc)
                elif isinstance(exc, ValueError):
                    code = "LOCAL_CONTEXT_TOO_LONG" if str(exc) == "LOCAL_CONTEXT_TOO_LONG" else "INVALID_LOCAL_INPUT"
                else:
                    code = "LOCAL_INFERENCE_FAILED"
                receipt = {"device_id": device_id, "job_id": item["id"], "success": False,
                           "result": {"error_code": code}}
            # No automatic rerun of inference or process actions after upload failure.
            with self._lock:
                self._pending_receipt = receipt
            try:
                api("/api/device/local-ai/result", receipt)
                with self._lock:
                    if self._pending_receipt is receipt:
                        self._pending_receipt = None
            except Exception:
                pass
        with self._lock:
            self._worker = threading.Thread(target=run, daemon=True,
                                            name="sonic-local-ai-job")
            self._worker.start()