"""Launch SONIC WiFi Finder. No console or Python needed in packaged builds."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="SONIC WiFi Finder — pemulihan Wi-Fi tersimpan")
    parser.add_argument("--demo", action="store_true", help="Gunakan data contoh tanpa membaca jaringan perangkat")
    parser.add_argument("--smoke-test", action="store_true", help="Uji startup singkat dengan data contoh")
    parser.add_argument("--smoke-report", type=Path, help="Simpan hasil uji startup tanpa data pribadi")
    parser.add_argument("--screenshot", type=Path, help="Simpan preview UI menggunakan data contoh, lalu keluar")
    args = parser.parse_args()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from sonic_wifi import __version__
    from sonic_wifi.backend import DemoBackend
    from sonic_wifi.ui import MainWindow
    app = QApplication(sys.argv[:1]); app.setApplicationName("SONIC WiFi Finder"); app.setApplicationVersion(__version__); app.setOrganizationName("SONIC")
    use_demo = args.demo or args.smoke_test or bool(args.screenshot)
    window = MainWindow(DemoBackend() if use_demo else None); window.show()
    if args.smoke_test or args.screenshot:
        def finish():
            font_ready = all(window.network_name.fontMetrics().inFont(c) for c in "SONICWiFiFinder0123456789")
            success = bool(window.networks.count()) and bool(window._selected) and window.password.text() == "" and window.reveal_btn.isEnabled() and font_ready
            if args.screenshot:
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                success = window.grab().save(str(args.screenshot)) and success
            if args.smoke_report:
                args.smoke_report.parent.mkdir(parents=True, exist_ok=True)
                args.smoke_report.write_text(json.dumps({"app":"SONIC WiFi Finder","version":__version__,"demo_only":True,"startup_ok":success,"profile_count":window.networks.count(),"password_initially_hidden":window.password.text()=="","font_ready":font_ready,"qt_platform":app.platformName()}, indent=2), encoding="utf-8")
            window.close(); app.exit(0 if success else 1)
        QTimer.singleShot(1800, finish)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
