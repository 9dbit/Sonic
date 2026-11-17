"""Build the current platform's desktop binary and a verifiable manifest.

Usage: python scripts/build_native.py
Run with an isolated environment containing requirements-build.txt.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "SONIC WiFi Finder"
VERSION = "1.0.0"


def run(*args: str) -> None:
    print("+ " + " ".join(str(x) for x in args), flush=True)
    subprocess.run([str(x) for x in args], cwd=str(ROOT), check=True)


def copy_runtime_notices() -> None:
    destination = ROOT / "licenses" / "runtime"
    destination.mkdir(parents=True, exist_ok=True)
    base = Path(sys.base_prefix)
    candidates = [base / "LICENSE.txt", base / "LICENSE", base / "lib" / ("python" + platform.python_version_tuple()[0] + "." + platform.python_version_tuple()[1]) / "LICENSE.txt"]
    for candidate in candidates:
        if candidate.is_file():
            shutil.copy2(candidate, destination / "Python-LICENSE.txt")
            break
    for package in ("PyInstaller", "PySide6-Essentials", "shiboken6"):
        dist = importlib.metadata.distribution(package)
        for path in dist.files or []:
            if "license" not in str(path).lower() and "copying" not in str(path).lower():
                continue
            actual = Path(dist.locate_file(path))
            if actual.is_file() and actual.suffix.lower() not in {".py", ".pyc", ".so", ".pyd", ".dll"}:
                target = destination / package / Path(str(path)).name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(actual, target)


def main() -> int:
    if sys.platform not in {"win32", "darwin"}:
        raise SystemExit("Native release builds require Windows or macOS. This script does not cross-compile.")
    if not (ROOT / "wifi_finder.py").is_file():
        raise SystemExit("Missing wifi_finder.py.")
    if not (ROOT / "licenses" / "LGPL-3.0.txt").is_file():
        raise SystemExit("Missing bundled license texts.")
    copy_runtime_notices()
    run(sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", str(ROOT / "SONIC-WiFi-Finder.spec"))
    dist = ROOT / "dist"
    if sys.platform == "win32":
        binary = dist / "SONIC-WiFi-Finder.exe"
        if binary.read_bytes()[:2] != b"MZ":
            raise SystemExit("Build output is not a Windows executable.")
        artifact = dist / ("SONIC-WiFi-Finder-" + VERSION + "-Windows-x64.exe")
        shutil.copy2(binary, artifact)
    else:
        app = dist / (APP_NAME + ".app")
        executable = app / "Contents" / "MacOS" / APP_NAME
        if not executable.is_file():
            raise SystemExit("Missing macOS application executable.")
        run("/usr/bin/codesign", "--verify", "--deep", "--strict", str(app))
        stage = ROOT / "build" / "dmg-content"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True)
        shutil.copytree(app, stage / app.name, symlinks=True)
        (stage / "Applications").symlink_to("/Applications", target_is_directory=True)
        (stage / "Mulai di sini.txt").write_text(
            "SONIC WiFi Finder 1.0.0\n\n"
            "Seret SONIC WiFi Finder.app ke Applications, lalu buka aplikasinya.\n"
            "Aplikasi memulihkan kata sandi jaringan yang tersimpan pada perangkat Anda.\n"
            "macOS dapat meminta persetujuan Keychain saat menampilkan kata sandi.\n\n"
            "Build ini memakai tanda tangan ad-hoc dan belum dinotarisasi Apple.\n"
            "Jika macOS memblokirnya, tinjau melalui System Settings > Privacy & Security.\n"
            "Jangan menonaktifkan Gatekeeper secara global.\n",
            encoding="utf-8",
        )
        arch = "AppleSilicon" if platform.machine() == "arm64" else "Intel"
        artifact = dist / ("SONIC-WiFi-Finder-" + VERSION + "-macOS-" + arch + ".dmg")
        if artifact.exists():
            artifact.unlink()
        run("/usr/bin/hdiutil", "create", "-volname", APP_NAME, "-srcfolder", str(stage), "-ov", "-format", "UDZO", str(artifact))
        run("/usr/bin/hdiutil", "verify", str(artifact))
    manifest = {
        "app": APP_NAME,
        "version": VERSION,
        "artifact": artifact.name,
        "size_bytes": artifact.stat().st_size,
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "dependencies": {name: importlib.metadata.version(name) for name in ("PyInstaller", "PySide6-Essentials", "shiboken6")},
        "signing": "ad-hoc, not Apple notarized" if sys.platform == "darwin" else "unsigned",
    }
    manifest_path = dist / (artifact.name + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
