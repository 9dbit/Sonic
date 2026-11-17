"""Local, explicit, single-profile Wi-Fi recovery through operating-system APIs.

Enumeration never requests key material. Only ``reveal(selected_profile)`` asks
the OS for a saved password, and every normal OS permission check remains in
place. No network requests, credential exports, logging, or privilege changes
are performed by this module.
"""

from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import threading
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class WifiProfile:
    id: str
    name: str
    interface: str = ""
    security: str = "Tersimpan"
    source: str = ""


class WifiError(Exception):
    """A message safe to show in the UI, without raw command output or keys."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _windows_error(code: int) -> WifiError:
    if code == 5:
        return WifiError(
            "permission_denied",
            "Windows belum mengizinkan akses ini. Buka Pengaturan Wi-Fi untuk "
            "melihat password, atau jalankan aplikasi sebagai administrator "
            "jika akun Anda berhak. Aplikasi tidak mengubah izin Windows.",
        )
    if code in (1062, 1068):
        return WifiError(
            "service_unavailable",
            "Layanan WLAN Windows tidak berjalan. Periksa adaptor Wi-Fi dan "
            "layanan WLAN AutoConfig melalui pengaturan Windows.",
        )
    if code in (1168, 2):
        return WifiError("not_found", "Profil Wi-Fi ini tidak ditemukan. Muat ulang daftar jaringan.")
    if code in (50, 120):
        return WifiError("unsupported", "Adapator atau versi Windows ini tidak mendukung pembacaan profil Wi-Fi.")
    return WifiError("os_error", f"Windows tidak dapat membaca profil Wi-Fi (kode {code}). Coba muat ulang daftar.")


def _profile_password(xml: str) -> str:
    """Extract only a plaintext personal-network key; never return encrypted data."""
    try:
        root = ET.fromstring(xml)
    except (ET.ParseError, TypeError):
        raise WifiError("invalid_profile", "Data profil Wi-Fi tidak dapat dibaca oleh aplikasi.") from None

    def value(path: str) -> str | None:
        element = root.find(path)
        return None if element is None else element.text

    security_path = "{*}MSM/{*}security/"
    authentication = (value(security_path + "{*}authEncryption/{*}authentication") or "").casefold()
    encryption = (value(security_path + "{*}authEncryption/{*}encryption") or "").casefold()
    use_onex = (value(security_path + "{*}authEncryption/{*}useOneX") or "").casefold()
    if use_onex == "true" or authentication in {"wpa", "wpa2", "wpa3ent", "wpa3ent192"}:
        raise WifiError(
            "enterprise",
            "Jaringan ini menggunakan autentikasi perusahaan (802.1X). Tidak ada "
            "satu password Wi-Fi bersama yang dapat ditampilkan dari profil ini.",
        )
    if authentication in {"open", "owe"} and encryption in {"none", "", "aes", "gcmp256"}:
        raise WifiError("no_password", "Jaringan ini tidak menyimpan password Wi-Fi bersama.")
    protected = (value(security_path + "{*}sharedKey/{*}protected") or "").casefold()
    if protected != "false":
        if protected == "true":
            raise WifiError(
                "permission_denied",
                "Windows mengembalikan kunci terenkripsi, bukan password yang dapat "
                "dibaca. Gunakan Pengaturan Wi-Fi atau akun yang memiliki izin.",
            )
        raise WifiError("not_found", "Profil tersimpan, tetapi password tidak tersedia untuk ditampilkan.")
    key = value(security_path + "{*}sharedKey/{*}keyMaterial")
    if key is None or key == "":
        raise WifiError("not_found", "Profil tersimpan, tetapi password tidak tersedia untuk ditampilkan.")
    return key  # Spaces are significant. Do not strip or log this value.


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_text(cls, text: str) -> "_GUID":
        return cls.from_buffer_copy(uuid.UUID(text).bytes_le)

    def as_text(self) -> str:
        return str(uuid.UUID(bytes_le=bytes(self)))


class _InterfaceInfo(ctypes.Structure):
    _fields_ = [("guid", _GUID), ("description", ctypes.c_wchar * 256), ("state", ctypes.c_uint32)]


class _ProfileInfo(ctypes.Structure):
    _fields_ = [("name", ctypes.c_wchar * 256), ("flags", ctypes.c_uint32)]


class _ListHeader(ctypes.Structure):
    _fields_ = [("count", ctypes.c_uint32), ("index", ctypes.c_uint32)]


class _WlanSession:
    """A short-lived WLAN handle. All buffers are released in their owner scope."""

    def __init__(self):
        if platform.system() != "Windows":
            raise WifiError("unsupported", "API WLAN hanya tersedia di Windows.")
        try:
            self.api = ctypes.WinDLL("wlanapi.dll")
        except (OSError, AttributeError):
            raise WifiError("unsupported", "Komponen Wi-Fi Windows tidak tersedia pada perangkat ini.") from None
        dword = ctypes.c_uint32
        pointer = ctypes.c_void_p
        self.api.WlanOpenHandle.argtypes = [dword, pointer, ctypes.POINTER(dword), ctypes.POINTER(pointer)]
        self.api.WlanOpenHandle.restype = dword
        self.api.WlanCloseHandle.argtypes = [pointer, pointer]
        self.api.WlanCloseHandle.restype = dword
        self.api.WlanEnumInterfaces.argtypes = [pointer, pointer, ctypes.POINTER(pointer)]
        self.api.WlanEnumInterfaces.restype = dword
        self.api.WlanGetProfileList.argtypes = [pointer, ctypes.POINTER(_GUID), pointer, ctypes.POINTER(pointer)]
        self.api.WlanGetProfileList.restype = dword
        self.api.WlanGetProfile.argtypes = [
            pointer, ctypes.POINTER(_GUID), ctypes.c_wchar_p, pointer,
            ctypes.POINTER(pointer), ctypes.POINTER(dword), ctypes.POINTER(dword),
        ]
        self.api.WlanGetProfile.restype = dword
        self.api.WlanFreeMemory.argtypes = [pointer]
        self.api.WlanFreeMemory.restype = None
        self.handle = pointer()

    def __enter__(self):
        negotiated = ctypes.c_uint32()
        result = self.api.WlanOpenHandle(2, None, ctypes.byref(negotiated), ctypes.byref(self.handle))
        if result:
            raise _windows_error(result)
        return self

    def __exit__(self, *_):
        if self.handle:
            self.api.WlanCloseHandle(self.handle, None)
            self.handle = ctypes.c_void_p()

    @staticmethod
    def _items(pointer: ctypes.c_void_p, item_type: type):
        if not pointer.value:
            return []
        header = ctypes.cast(pointer, ctypes.POINTER(_ListHeader)).contents
        if header.count > 100_000:
            raise WifiError("invalid_profile", "Daftar profil Wi-Fi yang dikembalikan Windows tidak valid.")
        start = pointer.value + ctypes.sizeof(_ListHeader)
        # Copy each item before the API-owned source buffer is freed.
        return [item_type.from_buffer_copy(ctypes.string_at(start + i * ctypes.sizeof(item_type), ctypes.sizeof(item_type))) for i in range(header.count)]

    def interfaces(self):
        buffer = ctypes.c_void_p()
        result = self.api.WlanEnumInterfaces(self.handle, None, ctypes.byref(buffer))
        try:
            if result:
                raise _windows_error(result)
            return self._items(buffer, _InterfaceInfo)
        finally:
            if buffer:
                self.api.WlanFreeMemory(buffer)

    def profiles(self, guid: _GUID):
        buffer = ctypes.c_void_p()
        result = self.api.WlanGetProfileList(self.handle, ctypes.byref(guid), None, ctypes.byref(buffer))
        try:
            if result:
                raise _windows_error(result)
            return self._items(buffer, _ProfileInfo)
        finally:
            if buffer:
                self.api.WlanFreeMemory(buffer)

    def password(self, guid: _GUID, name: str) -> str:
        buffer = ctypes.c_void_p()
        flags = ctypes.c_uint32(4)  # WLAN_PROFILE_GET_PLAINTEXT_KEY; OS permissions still apply.
        access = ctypes.c_uint32()
        result = self.api.WlanGetProfile(
            self.handle, ctypes.byref(guid), name, None, ctypes.byref(buffer), ctypes.byref(flags), ctypes.byref(access),
        )
        try:
            if result:
                raise _windows_error(result)
            if not buffer:
                raise WifiError("invalid_profile", "Windows tidak mengembalikan data profil Wi-Fi.")
            return _profile_password(ctypes.wstring_at(buffer))
        finally:
            if buffer:
                self.api.WlanFreeMemory(buffer)


class WindowsBackend:
    platform_name = "Windows"
    supports_manual = False

    def list_profiles(self) -> list[WifiProfile]:
        found = []
        with _WlanSession() as wlan:
            for interface in wlan.interfaces():
                guid = interface.guid.as_text()
                for saved in wlan.profiles(interface.guid):
                    found.append(WifiProfile(
                        id=f"{guid}:{saved.name}", name=saved.name,
                        interface=interface.description, source="Windows WLAN",
                    ))
        return sorted(found, key=lambda item: (item.name.casefold(), item.interface.casefold()))

    def reveal(self, profile: WifiProfile) -> str:
        try:
            guid_text, profile_name = profile.id.split(":", 1)
            guid = _GUID.from_text(guid_text)
            if not profile_name or "\x00" in profile_name or len(profile_name) > 255:
                raise ValueError
        except (ValueError, AttributeError):
            raise WifiError("invalid_profile", "Pilih profil dari daftar jaringan yang tersimpan.") from None
        with _WlanSession() as wlan:
            return wlan.password(guid, profile_name)

    def open_settings(self) -> None:
        try:
            os.startfile("ms-settings:network-wifi")
        except (OSError, AttributeError):
            raise WifiError("os_error", "Buka Settings > Network & internet > Wi-Fi secara manual.") from None

    def cancel_pending(self) -> None:
        # Native WLAN calls are short, synchronous OS calls; UI ignores stale results.
        pass


def _run_command(args: list[str], timeout: float = 20) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8", errors="strict",
            timeout=timeout, check=False, shell=False,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
    except subprocess.TimeoutExpired:
        raise WifiError("timeout", "Waktu tunggu habis. Selesaikan permintaan izin macOS, lalu coba lagi.") from None
    except UnicodeError:
        raise WifiError("invalid_profile", "Data Wi-Fi menggunakan format teks yang belum didukung aplikasi.") from None
    except OSError:
        raise WifiError("os_error", "Perintah Wi-Fi bawaan macOS tidak dapat dijalankan.") from None


def _wifi_devices(text: str) -> list[str]:
    devices = []
    hardware_port = ""
    for line in text.splitlines():
        if line.startswith("Hardware Port:"):
            hardware_port = line.partition(":")[2].strip()
        elif line.startswith("Device:") and hardware_port.casefold() in {"wi-fi", "airport", "wi‑fi"}:
            device = line.partition(":")[2].strip()
            if device and device not in devices:
                devices.append(device)
    return devices


def _preferred_names(text: str) -> list[str]:
    """networksetup uses one TAB as indentation; preserve SSID whitespace."""
    names = []
    for line in text.splitlines():
        if line.startswith("\t"):
            name = line[1:]
            if name and name not in names:
                names.append(name)
    return names


def _keychain_error(result: subprocess.CompletedProcess) -> WifiError:
    details = (result.stderr or "").casefold()
    if result.returncode == 44 or "could not be found" in details:
        return WifiError(
            "not_found",
            "Password jaringan ini tidak ditemukan di Keychain yang dapat diakses. "
            "Periksa nama jaringan atau lihat bagian Wi-Fi di aplikasi Passwords macOS.",
        )
    if result.returncode in (36, 51, 128) or any(word in details for word in ("denied", "canceled", "cancelled", "not allowed", "authorization")):
        return WifiError(
            "permission_denied",
            "Akses Keychain ditolak atau dibatalkan. Izinkan akses melalui dialog "
            "macOS jika Anda berhak, atau buka aplikasi Passwords secara langsung.",
        )
    return WifiError("os_error", "macOS belum dapat menampilkan password ini. Coba melalui aplikasi Passwords atau Keychain Access.")


class MacOSBackend:
    platform_name = "macOS"
    supports_manual = True

    def __init__(self, runner: Callable = _run_command):
        self._run = runner
        self._lock = threading.Lock()
        self._pending = None

    def cancel_pending(self) -> None:
        """Cancel only the child helper created by this backend, without waiting."""
        with self._lock:
            operation = self._pending
            if operation is None:
                return
            operation["cancelled"].set()
            process = operation["process"]
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def _security_command(self, args: list[str]) -> subprocess.CompletedProcess:
        # Injected runners keep unit tests independent from Keychain and macOS.
        if self._run is not _run_command:
            return self._run(args, timeout=90)
        operation = {"cancelled": threading.Event(), "process": None}
        with self._lock:
            if self._pending is not None:
                raise WifiError("busy", "Tunggu permintaan Keychain sebelumnya selesai.")
            self._pending = operation
        process = None
        try:
            if operation["cancelled"].is_set():
                raise WifiError("cancelled", "Permintaan password dibatalkan.")
            process = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="strict", shell=False,
                env={**os.environ, "LC_ALL": "C", "LANG": "C"},
            )
            with self._lock:
                operation["process"] = process
                cancelled = operation["cancelled"].is_set()
            if cancelled and process.poll() is None:
                process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=90)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise WifiError("timeout", "Waktu tunggu izin Keychain habis. Coba lagi setelah dialog macOS siap.") from None
            if operation["cancelled"].is_set():
                raise WifiError("cancelled", "Permintaan password dibatalkan.")
            return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
        except UnicodeError:
            raise WifiError("invalid_profile", "Password Keychain menggunakan format teks yang belum didukung.") from None
        except OSError:
            raise WifiError("os_error", "Permintaan Keychain tidak dapat dijalankan.") from None
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()
            with self._lock:
                if self._pending is operation:
                    self._pending = None

    def list_profiles(self) -> list[WifiProfile]:
        ports = self._run(["/usr/sbin/networksetup", "-listallhardwareports"])
        if ports.returncode:
            raise WifiError("permission_denied", "Daftar Wi-Fi tidak dapat dibaca. Anda masih dapat memasukkan nama jaringan secara manual.")
        found = []
        seen = set()
        failed = False
        for device in _wifi_devices(ports.stdout):
            result = self._run(["/usr/sbin/networksetup", "-listpreferredwirelessnetworks", device])
            if result.returncode:
                failed = True
                continue
            for name in _preferred_names(result.stdout):
                if name not in seen:
                    seen.add(name)
                    found.append(WifiProfile(
                        id=f"keychain:{name}", name=name, interface=device, source="macOS Keychain",
                    ))
        if failed and not found:
            raise WifiError("permission_denied", "macOS membatasi daftar jaringan tersimpan. Masukkan nama Wi-Fi secara manual atau buka aplikasi Passwords.")
        return sorted(found, key=lambda item: item.name.casefold())

    def manual_profile(self, name: str) -> WifiProfile:
        if not isinstance(name, str) or not name or "\x00" in name or len(name.encode("utf-8")) > 32:
            raise WifiError("invalid_profile", "Masukkan nama Wi-Fi persis seperti nama aslinya (maksimal 32 byte).")
        return WifiProfile(id=f"keychain:{name}", name=name, security="Belum diperiksa", source="macOS Keychain")

    def reveal(self, profile: WifiProfile) -> str:
        # Validate a single exact SSID and use an argv list, never a shell command.
        checked = self.manual_profile(profile.name)
        result = self._security_command(
            ["/usr/bin/security", "find-generic-password", "-D", "AirPort network password", "-a", checked.name, "-w"],
        )
        if result.returncode:
            raise _keychain_error(result)
        password = result.stdout[:-1] if result.stdout.endswith("\n") else result.stdout
        if not password:
            raise WifiError("not_found", "Keychain tidak mengembalikan password untuk jaringan ini.")
        return password

    def open_settings(self) -> None:
        result = self._run(["/usr/bin/open", "x-apple.systempreferences:com.apple.wifi-settings-extension"])
        if result.returncode:
            raise WifiError("os_error", "Buka System Settings > Wi-Fi secara manual.")

    def open_password_manager(self) -> None:
        result = self._run(["/usr/bin/open", "-a", "Passwords"])
        if result.returncode:
            result = self._run(["/usr/bin/open", "-a", "Keychain Access"])
        if result.returncode:
            raise WifiError("os_error", "Buka Passwords atau Keychain Access melalui Spotlight.")


class UnsupportedBackend:
    platform_name = platform.system()
    supports_manual = False

    def list_profiles(self) -> list[WifiProfile]:
        raise WifiError("unsupported", "Pemulihan Wi-Fi tersedia untuk Windows dan macOS. Gunakan mode demo untuk melihat antarmuka di perangkat ini.")

    def reveal(self, profile: WifiProfile) -> str:
        raise WifiError("unsupported", "Pemulihan Wi-Fi tersedia untuk Windows dan macOS.")

    def open_settings(self) -> None:
        raise WifiError("unsupported", "Buka pengaturan Wi-Fi perangkat Anda secara manual.")

    def cancel_pending(self) -> None:
        pass


class DemoBackend:
    """Synthetic UI fixtures; never calls OS Wi-Fi or credential APIs."""

    platform_name = "Demo"
    supports_manual = False

    def list_profiles(self) -> list[WifiProfile]:
        return [
            WifiProfile("demo:studio", "SONIC Studio", "Wi-Fi demo", "WPA2 Personal · Contoh", "Data demo"),
            WifiProfile("demo:home", "Rumah", "Wi-Fi demo", "WPA3 Personal · Contoh", "Data demo"),
            WifiProfile("demo:guest", "Meeting Room", "Wi-Fi demo", "Tanpa password · Contoh", "Data demo"),
        ]

    def reveal(self, profile: WifiProfile) -> str:
        if profile.id == "demo:guest":
            raise WifiError("no_password", "Jaringan contoh ini tidak menggunakan password Wi-Fi.")
        if profile.id not in {"demo:studio", "demo:home"}:
            raise WifiError("not_found", "Jaringan contoh tidak ditemukan.")
        return "SonicDemo2026!" if profile.id == "demo:studio" else "RumahDemo2026!"

    def open_settings(self) -> None:
        raise WifiError("demo", "Ini adalah mode demo. Pengaturan perangkat tidak dibuka.")

    def cancel_pending(self) -> None:
        pass


def backend_for_platform():
    system = platform.system()
    if system == "Windows":
        return WindowsBackend()
    if system == "Darwin":
        return MacOSBackend()
    return UnsupportedBackend()
