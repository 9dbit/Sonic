"""Limited-user WinGet broker for SONIC. Importing this module has no side effects.

Only structured software actions are accepted. The web approval must bind the
same plan hash returned by inspection. This local check is an additional gate,
not a replacement for owner/device authentication in the companion API.

CLI metadata is returned as bounded, unparsed evidence. Installed versions are
verified only from WinGet's JSON export; an installer exit code is not proof of
installation. An interrupted install is never automatically replayed.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable


SOURCE_NAME = "winget"
SOURCE_URL = "https://cdn.winget.microsoft.com/cache"
SOURCE_TYPE = "Microsoft.PreIndexed.Package"
SOURCE_ID = "Microsoft.Winget.Source_8wekyb3d8bbwe"
MAX_OUTPUT = 12000
MAX_RESPONSE_BYTES = 30000
MAX_INVENTORY_BYTES = 2 * 1024 * 1024
PLAN_TTL_SECONDS = 1800
INSTALL_TIMEOUT_SECONDS = 1200
PACKAGE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{1,127}\Z")
VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,79}\Z")
QUERY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._+-]{0,119}\Z")
PLAN_KEYS = frozenset(("package_id", "version", "source", "scope",
                       "accept_source_agreements", "accept_package_agreements",
                       "allow_reboot"))


def plan_sha256(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()


def _encoded_size(value) -> int:
    # The companion JSON encoder uses ensure_ascii=True. Counting these bytes is
    # conservative for both escaped JSON and unescaped UTF-8 HTTP serializers.
    return len(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))


def _bounded_text(value: str, budget: int) -> tuple[str, bool]:
    if _encoded_size(value) <= budget:
        return value, False
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        if _encoded_size(value[:middle]) <= budget:
            low = middle
        else:
            high = middle - 1
    return value[:low], True


def _safe_env() -> dict:
    """Do not pass SONIC credentials or provider keys into vendor installers."""
    allowed = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP",
               "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA",
               "APPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432",
               "PROGRAMDATA", "ALLUSERSPROFILE", "USERNAME", "USERDOMAIN", "OS",
               "PROCESSOR_ARCHITECTURE", "PROCESSOR_ARCHITEW6432",
               "NUMBER_OF_PROCESSORS", "COMMONPROGRAMFILES",
               "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432"}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


@dataclass
class ProcessResult:
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    cancelled: bool = False
    cancellation_requested: bool = False
    pid: int | None = None
    process_running: bool = False
    truncated: bool = False


def run_process(argv: list[str], *, timeout_seconds: int,
                mutation: bool = False, on_tick: Callable | None = None,
                cancel_requested: Callable | None = None) -> ProcessResult:
    """Bound output and keep heartbeats alive without terminating an installer.

    A timeout/cancel during a mutation never kills the MSI/installer process tree.
    The caller must retain its journal and report reconciliation_required.
    """
    def cancelled() -> bool:
        try:
            return bool(cancel_requested and cancel_requested())
        except Exception:
            return True  # Unknown lease state cannot authorize new side effects.

    if cancelled():
        return ProcessResult(None, cancelled=True, cancellation_requested=True)
    proc = subprocess.Popen(argv, shell=False, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=_safe_env(), creationflags=(getattr(subprocess,
                            "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0))
    buffers: list[bytearray] = [bytearray(), bytearray()]
    truncated = [False, False]

    def drain(stream, index):
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                remaining = MAX_OUTPUT * 4 - len(buffers[index])
                if remaining > 0:
                    buffers[index].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    truncated[index] = True
        finally:
            stream.close()

    threads = [threading.Thread(target=drain, args=(proc.stdout, 0), daemon=True),
               threading.Thread(target=drain, args=(proc.stderr, 1), daemon=True)]
    for thread in threads:
        thread.start()
    start = time.monotonic()
    next_tick = start
    cancellation_seen = False
    timed_out = False
    was_cancelled = False
    while proc.poll() is None:
        now = time.monotonic()
        cancellation_seen = cancellation_seen or cancelled()
        if now >= next_tick:
            if on_tick:
                try:
                    on_tick({"pid": proc.pid, "elapsed_seconds": int(now - start),
                             "cancellation_requested": cancellation_seen})
                except Exception:
                    cancellation_seen = True
            next_tick = now + 5
        if cancellation_seen and not mutation:
            was_cancelled = True
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            break
        if now - start >= timeout_seconds:
            timed_out = True
            if not mutation:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            break
        time.sleep(0.2)
    running = proc.poll() is None
    if not running:
        for thread in threads:
            thread.join(timeout=2)
    out = [bytes(buf).decode("utf-8-sig", errors="replace") for buf in buffers]
    return ProcessResult(proc.poll(), out[0][:MAX_OUTPUT], out[1][:MAX_OUTPUT],
                         timed_out, was_cancelled, cancellation_seen, proc.pid,
                         running, any(truncated) or any(len(s) > MAX_OUTPUT for s in out))


def _windows_identity() -> dict:
    """Read the actual token SID/elevation, not spoofable USERNAME variables."""
    from ctypes import wintypes
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                       ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,
                                             ctypes.POINTER(wintypes.LPWSTR)]
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008,
                                  ctypes.byref(token)):
        raise OSError("TOKEN_UNAVAILABLE")
    try:
        needed = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
        if not 0 < needed.value < 65536:
            raise OSError("TOKEN_USER_UNAVAILABLE")
        buffer = ctypes.create_string_buffer(needed.value)
        if not advapi.GetTokenInformation(token, 1, buffer, needed,
                                         ctypes.byref(needed)):
            raise OSError("TOKEN_USER_UNAVAILABLE")
        sid_pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        sid_text = wintypes.LPWSTR()
        if not advapi.ConvertSidToStringSidW(sid_pointer, ctypes.byref(sid_text)):
            raise OSError("TOKEN_SID_UNAVAILABLE")
        try:
            sid = sid_text.value
        finally:
            kernel.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
        elevation = wintypes.DWORD()
        if not advapi.GetTokenInformation(token, 20, ctypes.byref(elevation),
            ctypes.sizeof(elevation), ctypes.byref(needed)):
            raise OSError("TOKEN_ELEVATION_UNAVAILABLE")
        return {"sid": sid, "elevated": bool(elevation.value)}
    finally:
        kernel.CloseHandle(token)


def _find_winget() -> str | None:
    """Only use the Windows App Installer location, never current-directory PATH."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidate = Path(local) / "Microsoft" / "WindowsApps" / "winget.exe"
        if candidate.is_file():
            return str(candidate)
    candidate = shutil.which("winget.exe")
    program_files = os.environ.get("ProgramFiles")
    if candidate and program_files:
        parent = Path(program_files) / "WindowsApps"
        try:
            relative = Path(candidate).absolute().relative_to(parent.absolute())
        except ValueError:
            return None
        if (len(relative.parts) == 2 and
            relative.parts[0].startswith("Microsoft.DesktopAppInstaller_") and
            relative.parts[1].lower() == "winget.exe" and Path(candidate).is_file()):
            return candidate
    return None


def _private_directory(path: Path, sid: str | None = None) -> None:
    if path.is_symlink():
        raise OSError("STATE_DIRECTORY_SYMLINK")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)
        return
    if not sid or not re.fullmatch(r"S-1-[0-9-]+", sid):
        raise OSError("STATE_DIRECTORY_IDENTITY_UNKNOWN")
    from ctypes import wintypes
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD)]
    advapi.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                      ctypes.c_void_p]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    descriptor = ctypes.c_void_p()
    # Protected DACL: this user and SYSTEM; no inherited broad write access.
    sddl = "D:P(A;OICI;FA;;;" + sid + ")(A;OICI;FA;;;SY)"
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(descriptor), None):
        raise OSError("PRIVATE_DIRECTORY_ACL_FAILED")
    try:
        if not advapi.SetFileSecurityW(str(path), 0x80000004, descriptor):
            raise OSError("PRIVATE_DIRECTORY_ACL_FAILED")
    finally:
        kernel.LocalFree(descriptor)


class WindowsSoftwareBroker:
    """Execute one approved structured operation with limited-user privileges.

    on_progress receives a dict at state changes and roughly every five seconds.
    cancel_requested returns true if cancelled or lease is no longer valid.
    Both callbacks must return promptly; API callbacks should use bounded timeouts.
    Dependency injection is for offline tests, never accepted from task payloads.
    """
    def __init__(self, state_dir: Path | str | None = None, *, runner=run_process,
                 identity_probe=None, winget_resolver=None, platform_name=None,
                 discovery_enabled: bool | None = None,
                 install_enabled: bool | None = None, clock=time.time):
        default = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SONIC" / "software"
        self.state_dir = Path(state_dir) if state_dir is not None else default
        self.runner = runner
        self.identity_probe = identity_probe or _windows_identity
        self.winget_resolver = winget_resolver or _find_winget
        self.platform_name = sys.platform if platform_name is None else platform_name
        self.discovery_enabled = (os.environ.get("SONIC_SOFTWARE_DISCOVERY_ENABLED") == "1"
                                  if discovery_enabled is None else discovery_enabled)
        self.install_enabled = (os.environ.get("SONIC_SOFTWARE_INSTALL_ENABLED") == "1"
                                if install_enabled is None else install_enabled)
        self.clock = clock
        self._winget = None
        self._sid = None

    @staticmethod
    def _failure(code, *, status="blocked", **extra):
        return {"ok": False, "status": status, "code": code, **extra}

    @staticmethod
    def _evidence(proc: ProcessResult, kind="winget_cli_raw") -> dict:
        stdout, stdout_cut = _bounded_text(proc.stdout, 6000)
        stderr, stderr_cut = _bounded_text(proc.stderr, 2000)
        return {"kind": kind, "exit_code": proc.exit_code,
                "stdout": stdout, "stderr": stderr,
                "truncated": proc.truncated or stdout_cut or stderr_cut,
                "timed_out": proc.timed_out, "process_running": proc.process_running}

    @staticmethod
    def _bounded_result(result: dict) -> dict:
        if _encoded_size(result) <= MAX_RESPONSE_BYTES:
            return result
        result["response_truncated"] = True
        evidence_sets = []

        def reduce_debug(value):
            if isinstance(value, dict):
                if value.get("kind") == "winget_export_json" and isinstance(value.get("packages"), list):
                    evidence_sets.append(value)
                for key, child in list(value.items()):
                    if key in {"stdout", "stderr"} and isinstance(child, str):
                        value[key], cut = _bounded_text(child, 512)
                        if cut:
                            value["truncated"] = True
                    else:
                        reduce_debug(child)
            elif isinstance(value, list):
                for child in value:
                    reduce_debug(child)
        reduce_debug(result)
        for evidence in evidence_sets:
            while _encoded_size(result) > MAX_RESPONSE_BYTES and len(evidence["packages"]) > 1:
                evidence["packages"].pop()
                evidence["truncated"] = True
        if _encoded_size(result) > MAX_RESPONSE_BYTES:
            # Fixed small result rather than an HTTP rejection after side effects.
            return {"ok": False, "status": "reconciliation_required", "code": "RESULT_TOO_LARGE",
                    "plan_sha256": result.get("plan_sha256"), "installer_replayed": False}
        return result

    @staticmethod
    def _cancelled(callback):
        try:
            return bool(callback and callback())
        except Exception:
            return True

    @staticmethod
    def _validate(action, payload):
        if not isinstance(payload, dict):
            raise ValueError("PAYLOAD_INVALID")
        fields = {
            "software.search": {"query", "accept_source_agreements"},
            "software.inspect": {"package_id", "version", "accept_source_agreements",
                                 "accept_package_agreements"},
            "software.inventory": set(),
            "software.install": {"plan", "plan_sha256"},
        }
        if action not in fields or set(payload) != fields[action]:
            raise ValueError("ACTION_OR_FIELDS_INVALID")
        for key in ("accept_source_agreements", "accept_package_agreements"):
            if key in payload and type(payload[key]) is not bool:
                raise ValueError("AGREEMENT_FLAG_MUST_BE_BOOLEAN")
        if action == "software.search":
            if not isinstance(payload["query"], str) or not QUERY_RE.fullmatch(payload["query"]):
                raise ValueError("QUERY_INVALID")
        if action == "software.inspect":
            if not isinstance(payload["package_id"], str) or not PACKAGE_RE.fullmatch(payload["package_id"]):
                raise ValueError("PACKAGE_ID_INVALID")
            if not isinstance(payload["version"], str) or not VERSION_RE.fullmatch(payload["version"]):
                raise ValueError("VERSION_INVALID")
            if payload["version"].lower() in {"latest", "stable", "current", "any"}:
                raise ValueError("PINNED_VERSION_REQUIRED")
        if action == "software.install":
            plan = payload["plan"]
            if not isinstance(plan, dict) or set(plan) != PLAN_KEYS:
                raise ValueError("PLAN_INVALID")
            WindowsSoftwareBroker._validate("software.inspect", {key: plan[key] for key in
                ("package_id", "version", "accept_source_agreements", "accept_package_agreements")})
            if plan["source"] != SOURCE_NAME or plan["scope"] != "user" or plan["allow_reboot"] is not False:
                raise ValueError("PLAN_POLICY_INVALID")
            digest = payload["plan_sha256"]
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("PLAN_HASH_INVALID")
            if digest != plan_sha256(plan):
                raise ValueError("PLAN_HASH_MISMATCH")

    def preflight(self) -> dict:
        """Local token/client/source checks only; never search, install or accept terms."""
        if self.platform_name != "win32":
            return self._failure("WINDOWS_ONLY")
        try:
            identity = self.identity_probe()
            sid = identity.get("sid")
            if not isinstance(sid, str) or not re.fullmatch(r"S-1-[0-9-]+", sid):
                return self._failure("USER_IDENTITY_UNKNOWN")
            if sid in {"S-1-5-18", "S-1-5-19", "S-1-5-20"}:
                return self._failure("WINGET_CLI_SERVICE_CONTEXT_UNSUPPORTED")
            if identity.get("elevated") is not False:
                return self._failure("LIMITED_USER_REQUIRED")
            winget = self.winget_resolver()
            if not isinstance(winget, str) or not winget:
                return self._failure("WINGET_NOT_AVAILABLE")
            version = self.runner([winget, "--version"], timeout_seconds=15)
            if version.exit_code != 0 or version.timed_out:
                return self._failure("WINGET_CLIENT_UNAVAILABLE")
            source_proc = self.runner([winget, "source", "export", "--name", SOURCE_NAME,
                                       "--disable-interactivity"], timeout_seconds=15)
            if source_proc.exit_code != 0 or source_proc.truncated or source_proc.timed_out:
                return self._failure("WINGET_SOURCE_UNVERIFIED")
            source = json.loads(source_proc.stdout.lstrip("\ufeff"))
            if not self._source_matches(source, "Arg"):
                return self._failure("WINGET_SOURCE_IDENTITY_MISMATCH")
            self._winget, self._sid = winget, sid
            return {"ok": True, "status": "ready", "winget_version": version.stdout.strip()[:64],
                    "limited_user": True, "source": SOURCE_NAME,
                    "source_identity_verified": True, "requested_scope": "user",
                    "discovery_enabled": self.discovery_enabled,
                    "install_enabled": self.install_enabled}
        except (OSError, ValueError, TypeError, AttributeError):
            return self._failure("PREFLIGHT_UNAVAILABLE")

    @staticmethod
    def _source_matches(source, argument_key):
        return (isinstance(source, dict) and source.get("Name") == SOURCE_NAME and
                source.get(argument_key) == SOURCE_URL and source.get("Type") == SOURCE_TYPE and
                source.get("Identifier") == SOURCE_ID)

    def _prepare_state(self):
        _private_directory(self.state_dir, self._sid)
        for subdir in ("plans", "journal", "temporary"):
            _private_directory(self.state_dir / subdir, self._sid)

    @staticmethod
    def _write_json(path: Path, value: dict):
        if path.is_symlink():
            raise OSError("STATE_FILE_SYMLINK")
        fd, temporary = tempfile.mkstemp(prefix="write-", suffix=".json", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _read_json(path: Path, maximum=128000):
        if path.is_symlink() or path.stat().st_size > maximum:
            raise ValueError("STATE_FILE_INVALID")
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _command(self, args, *, on_progress=None, cancel_requested=None,
                 mutation=False, phase="checking", timeout_seconds=90):
        def tick(info):
            if on_progress:
                on_progress({"phase": phase, **info})
        return self.runner([self._winget, *args], timeout_seconds=timeout_seconds,
                           mutation=mutation, on_tick=tick,
                           cancel_requested=cancel_requested)

    def handle(self, action: str, payload: dict, *, task_id: str | None = None,
               on_progress: Callable | None = None,
               cancel_requested: Callable | None = None) -> dict:
        return self._bounded_result(self._handle(action, payload, task_id=task_id,
            on_progress=on_progress, cancel_requested=cancel_requested))

    def _handle(self, action: str, payload: dict, *, task_id: str | None = None,
                on_progress: Callable | None = None,
                cancel_requested: Callable | None = None) -> dict:
        try:
            self._validate(action, payload)
        except (ValueError, TypeError) as exc:
            return self._failure(str(exc))
        if not self.discovery_enabled:
            return self._failure("SOFTWARE_DISCOVERY_LOCAL_DISABLED")
        if action == "software.install" and not self.install_enabled:
            return self._failure("SOFTWARE_INSTALL_LOCAL_DISABLED")
        if self._cancelled(cancel_requested):
            return self._failure("TASK_CANCELLED_OR_LEASE_LOST", status="cancelled")
        ready = self.preflight()
        if not ready["ok"]:
            return ready
        try:
            self._prepare_state()
            if action == "software.install":
                return self._install(payload, task_id, on_progress, cancel_requested)
            if action == "software.inventory":
                return self._inventory(False, on_progress, cancel_requested)
            if action == "software.search":
                args = ["search", "--query", payload["query"], "--source", SOURCE_NAME,
                        "--count", "20", "--disable-interactivity"]
                kind = "winget_search_raw"
            else:
                args = ["show", "--id", payload["package_id"], "--exact", "--version",
                        payload["version"], "--source", SOURCE_NAME, "--scope", "user",
                        "--disable-interactivity"]
                kind = "winget_show_raw"
            if payload["accept_source_agreements"]:
                args.append("--accept-source-agreements")
            proc = self._command(args, on_progress=on_progress,
                                 cancel_requested=cancel_requested, phase="discovering")
            evidence = self._evidence(proc, kind)
            if proc.cancelled:
                return self._failure("TASK_CANCELLED_OR_LEASE_LOST", status="cancelled", evidence=evidence)
            if proc.exit_code != 0 or proc.timed_out:
                return self._failure("WINGET_DISCOVERY_INCOMPLETE", status="requires_user_action", evidence=evidence)
            if action == "software.inspect" and not proc.stdout.strip():
                return self._failure("INSPECTION_METADATA_EMPTY", status="requires_user_action", evidence=evidence)
            result = {"ok": True, "status": "searched", "evidence": evidence,
                      "metadata_parsed": False, "source_identity_verified": True,
                      "publisher_signature_verified": False}
            if action == "software.inspect":
                plan = {**payload, "source": SOURCE_NAME, "scope": "user", "allow_reboot": False}
                digest = plan_sha256(plan)
                self._write_json(self.state_dir / "plans" / (digest + ".json"),
                    {"plan": plan, "plan_sha256": digest, "created_at": self.clock(),
                     "expires_at": self.clock() + PLAN_TTL_SECONDS,
                     "source_identity_verified": True, "inspection_exit_code": 0})
                result.update(status="inspected", plan=plan, plan_sha256=digest,
                              plan_expires_in_seconds=PLAN_TTL_SECONDS)
            return result
        except (OSError, ValueError, TypeError, KeyError) as exc:
            # Do not include exception text with paths, credentials or installer output.
            return self._failure("SOFTWARE_BROKER_UNAVAILABLE", status="failed",
                                 error_type=type(exc).__name__)

    def _inventory(self, accept_source_agreements, on_progress, cancel_requested,
                   *, package_id=None):
        temporary = Path(tempfile.mkdtemp(prefix="inventory-", dir=self.state_dir / "temporary"))
        _private_directory(temporary, self._sid)
        output = temporary / "inventory.json"
        try:
            args = ["export", "--output", str(output), "--source", SOURCE_NAME,
                    "--include-versions", "--disable-interactivity"]
            if accept_source_agreements:
                args.append("--accept-source-agreements")
            proc = self._command(args, on_progress=on_progress,
                cancel_requested=cancel_requested, phase="verifying_inventory")
            process_evidence = self._evidence(proc)
            if package_id is not None:
                # Export warnings may name unrelated apps that were not matched
                # to a catalog. An install of one package does not need those names.
                process_evidence.pop("stdout", None)
                process_evidence.pop("stderr", None)
                process_evidence["raw_output_omitted"] = True
            if proc.cancelled:
                return self._failure("TASK_CANCELLED_OR_LEASE_LOST", status="cancelled",
                                     process=process_evidence)
            if proc.exit_code != 0 or proc.timed_out or not output.is_file():
                return self._failure("INVENTORY_EVIDENCE_UNAVAILABLE", status="requires_user_action",
                                     process=process_evidence)
            data = self._read_json(output, MAX_INVENTORY_BYTES)
            if not isinstance(data, dict) or not isinstance(data.get("Sources"), list):
                raise ValueError("INVENTORY_SCHEMA_INVALID")
            packages = []
            for source in data["Sources"]:
                if not isinstance(source, dict) or not self._source_matches(source.get("SourceDetails"), "Argument"):
                    return self._failure("INVENTORY_SOURCE_IDENTITY_MISMATCH")
                entries = source.get("Packages")
                if not isinstance(entries, list):
                    raise ValueError("INVENTORY_SCHEMA_INVALID")
                for entry in entries:
                    if not isinstance(entry, dict):
                        raise ValueError("INVENTORY_SCHEMA_INVALID")
                    identifier, version = entry.get("PackageIdentifier"), entry.get("Version")
                    if not isinstance(identifier, str) or not PACKAGE_RE.fullmatch(identifier):
                        raise ValueError("INVENTORY_PACKAGE_INVALID")
                    if package_id is not None and identifier != package_id:
                        continue
                    # Unknown/missing versions remain explicit; never substitute requested/latest.
                    packages.append({"package_id": identifier,
                        "version": version if isinstance(version, str) and len(version) <= 120 else None,
                        "source": SOURCE_NAME})
            bounded_packages = []
            package_bytes = 0
            for package in packages:
                size = _encoded_size(package) + 1
                if len(bounded_packages) >= 250 or package_bytes + size > 16000:
                    break
                bounded_packages.append(package)
                package_bytes += size
            evidence = {"kind": "winget_export_json", "packages": bounded_packages,
                        "truncated": len(packages) > len(bounded_packages), "source_identity_verified": True,
                        "matched_package_count": len(packages), "exit_code": proc.exit_code}
            return {"ok": True, "status": "inventoried", "evidence": evidence,
                    "coverage": "winget_catalog_matched_packages_only", "process": process_evidence,
                    "scope_verified": False}
        finally:
            # Only this broker-created directory is removed; no user file path is accepted.
            shutil.rmtree(temporary, ignore_errors=True)

    def _install(self, payload, task_id, on_progress, cancel_requested):
        plan, digest = payload["plan"], payload["plan_sha256"]
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", task_id):
            return self._failure("INSTALL_TASK_ID_REQUIRED")
        if not plan["accept_source_agreements"] or not plan["accept_package_agreements"]:
            return self._failure("EXPLICIT_AGREEMENT_ACCEPTANCE_REQUIRED")
        journal = self.state_dir / "journal" / (hashlib.sha256(task_id.encode()).hexdigest() + ".json")
        if journal.exists():
            prior = self._read_json(journal)
            if prior.get("plan_sha256") != digest:
                return self._failure("TASK_PLAN_CHANGED")
            if isinstance(prior.get("result"), dict):
                return {**prior["result"], "replayed_result": True, "installer_replayed": False}
            return self._failure("PREVIOUS_INSTALL_OUTCOME_UNKNOWN", status="reconciliation_required",
                                 plan_sha256=digest, installer_replayed=False)
        plan_path = self.state_dir / "plans" / (digest + ".json")
        if not plan_path.is_file():
            return self._failure("LOCAL_INSPECTION_REQUIRED")
        inspected = self._read_json(plan_path)
        if (inspected.get("plan") != plan or inspected.get("plan_sha256") != digest or
            inspected.get("inspection_exit_code") != 0 or
            inspected.get("source_identity_verified") is not True):
            return self._failure("LOCAL_INSPECTION_INVALID")
        if not isinstance(inspected.get("expires_at"), (int, float)) or self.clock() > inspected["expires_at"]:
            return self._failure("LOCAL_INSPECTION_EXPIRED")
        lock = self.state_dir / "install.lock"
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return self._failure("INSTALL_LOCK_REQUIRES_RECONCILIATION", status="reconciliation_required")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"task_id": task_id, "plan_sha256": digest, "created_at": self.clock()}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        started = False
        retain_lock = False

        def record(result):
            self._write_json(journal, {"task_id": task_id, "plan_sha256": digest,
                "updated_at": self.clock(), "installer_started": started, "result": result})
            return result

        try:
            before = self._inventory(True, on_progress, cancel_requested,
                                     package_id=plan["package_id"])
            if not before["ok"]:
                return record(self._failure("INSTALL_PREFLIGHT_INVENTORY_UNAVAILABLE",
                    status=before["status"], detail=before, plan_sha256=digest))
            existing = before["evidence"]["packages"]
            if any(p["version"] == plan["version"] for p in existing):
                return record(self._success("already_installed", plan, digest, before["evidence"]))
            if existing:
                return record(self._failure("EXISTING_VERSION_REQUIRES_SEPARATE_ACTION",
                    plan_sha256=digest, evidence=before["evidence"]))
            if self._cancelled(cancel_requested):
                return record(self._failure("TASK_CANCELLED_OR_LEASE_LOST", status="cancelled",
                                            plan_sha256=digest))
            # Recheck source identity immediately before launching the mutation.
            if not self.preflight()["ok"]:
                return record(self._failure("INSTALL_PREFLIGHT_CHANGED", plan_sha256=digest))
            if self._cancelled(cancel_requested):
                return record(self._failure("TASK_CANCELLED_OR_LEASE_LOST", status="cancelled",
                                            plan_sha256=digest))
            self._write_json(journal, {"task_id": task_id, "plan_sha256": digest,
                "updated_at": self.clock(), "state": "launching", "installer_started": False})
            args = ["install", "--id", plan["package_id"], "--exact", "--version", plan["version"],
                    "--source", SOURCE_NAME, "--dependency-source", SOURCE_NAME,
                    "--scope", "user", "--silent", "--disable-interactivity",
                    "--no-upgrade", "--accept-source-agreements", "--accept-package-agreements"]
            started = True  # Crash after dispatch must never cause automatic replay.
            proc = self._command(args, on_progress=on_progress,
                cancel_requested=cancel_requested, mutation=True, phase="installing",
                timeout_seconds=INSTALL_TIMEOUT_SECONDS)
            process_evidence = self._evidence(proc)
            if proc.cancelled and proc.pid is None:
                started = False
                return record(self._failure("TASK_CANCELLED_OR_LEASE_LOST", status="cancelled",
                                            plan_sha256=digest, process=process_evidence))
            if proc.timed_out or proc.process_running:
                retain_lock = True
                return record(self._failure("INSTALL_OUTCOME_UNKNOWN", status="reconciliation_required",
                    plan_sha256=digest, process=process_evidence, pid=proc.pid,
                    installer_replayed=False, cancellation_requested=proc.cancellation_requested))
            # Once dispatched, verification is read-only and continues after lease loss.
            # No install retry, process termination, reboot or rollback is attempted.
            after = self._inventory(True, on_progress, None, package_id=plan["package_id"])
            matched = after.get("ok") and any(p["version"] == plan["version"]
                        for p in after["evidence"]["packages"])
            if proc.exit_code == 0 and matched:
                return record(self._success("succeeded", plan, digest, after["evidence"],
                    process=process_evidence, cancellation_requested=proc.cancellation_requested))
            # An installer failure or missing version is never relabelled success.
            # WinGet exit codes are NOT treated as raw MSI 3010/1641 return codes.
            retain_lock = True
            return record(self._failure("INSTALL_NOT_VERIFIED", status="reconciliation_required",
                plan_sha256=digest, process=process_evidence,
                evidence=after.get("evidence", {}), verification={"status": "unverified"},
                cancellation_requested=proc.cancellation_requested,
                requested_scope="user", installer_replayed=False))
        except Exception as exc:
            retain_lock = started
            result = self._failure("INSTALL_OUTCOME_UNKNOWN" if started else "INSTALL_PRECHECK_FAILED",
                status="reconciliation_required" if started else "failed", plan_sha256=digest,
                installer_replayed=False, error_type=type(exc).__name__)
            try:
                return record(result)
            except (OSError, ValueError):
                return result
        finally:
            if not retain_lock:
                try:
                    lock.unlink()
                except FileNotFoundError:
                    pass

    @staticmethod
    def _success(status, plan, digest, evidence, **extra):
        observed = next(package for package in evidence["packages"]
            if package.get("package_id") == plan["package_id"] and
            package.get("version") == plan["version"] and package.get("source") == SOURCE_NAME)
        scoped_evidence = {**evidence, "packages": [dict(observed)],
                           "filtered_to_requested_version": True}
        return {"ok": True, "status": status, "plan_sha256": digest,
                "installed": dict(observed), "requested_scope": "user",
                "scope_verified": False, "evidence": scoped_evidence,
                "verification": {"status": "agent_verified", "method": "winget_export_json"},
                "installer_replayed": False, **extra}
