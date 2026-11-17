"""A small, local-first desktop interface for saved Wi-Fi recovery."""
from __future__ import annotations

import secrets
import struct
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QByteArray, QEvent, QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from sonic_wifi import __version__
from sonic_wifi.backend import DemoBackend, WifiError, WifiProfile, backend_for_platform


STYLE = """
QWidget { color: #e8edf5; font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 13px; }
QMainWindow, QDialog { background: #0b1018; }
QFrame#card { background: #131b27; border: 1px solid #263143; border-radius: 18px; }
QFrame#inner { background: #0e1520; border: 1px solid #2b394d; border-radius: 12px; }
QLabel { background: transparent; border: none; }
QLabel#muted { color: #a7b4c7; }
QLabel#eyebrow { color: #8eaae0; font-size: 11px; font-weight: 700; }
QLabel#pill { background: #18283c; color: #a6c8ff; border: 1px solid #2d4567; border-radius: 12px; padding: 5px 12px; font-size: 11px; }
QLabel#notice { color: #9fc6ff; background: #14233a; border-radius: 10px; padding: 10px 12px; }
QLabel#error { color: #ffcf9d; background: #30251d; border-radius: 10px; padding: 10px 12px; }
QPushButton { background: #1c293b; border: 1px solid #34465f; border-radius: 10px; padding: 10px 14px; font-weight: 600; }
QPushButton:hover { background: #253951; border-color: #5379af; }
QPushButton:pressed { background: #111e2f; }
QPushButton:focus { border: 2px solid #91baff; }
QPushButton:disabled { color: #64748b; background: #172131; border-color: #263143; }
QPushButton#primary { background: #4285f4; color: #ffffff; border: 1px solid #4285f4; padding: 12px 18px; }
QPushButton#primary:hover { background: #619bfa; border-color: #619bfa; }
QPushButton#primary:pressed { background: #2c65c3; }
QPushButton#primary:disabled { background: #243b5d; color: #8199bc; border-color: #2a4161; }
QPushButton#quiet { background: transparent; border-color: transparent; color: #a7b4c7; padding: 7px 8px; }
QPushButton#quiet:hover { color: #e8edf5; background: #1c293b; }
QLineEdit { background: #0e1520; border: 1px solid #2b394d; border-radius: 10px; padding: 10px 12px; selection-background-color: #315f9b; }
QLineEdit:focus { border: 1px solid #659af2; }
QLineEdit:disabled { color: #64748b; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { border: 1px solid transparent; border-radius: 10px; padding: 12px 10px; margin: 2px 0; }
QListWidget::item:hover { background: #1a2739; }
QListWidget::item:selected { background: #1b3253; border: 1px solid #365b8a; color: #f0f6ff; }
QListWidget::item:focus { border: 1px solid #90b9ff; }
QScrollBar:vertical { border: none; background: transparent; width: 7px; margin: 3px 0; }
QScrollBar::handle:vertical { background: #36475f; min-height: 24px; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QToolTip { background: #1c293b; color: #e8edf5; border: 1px solid #435a79; padding: 5px; }
"""


def asset_path(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "assets" / name


def icon(kind: str, color: str = "#a9c9ff", size: int = 24) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(2)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24, size / 24)
    p.setPen(QPen(QColor(color), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind == "wifi":
        p.drawArc(1, 3, 22, 22, 45 * 16, 90 * 16)
        p.drawArc(5, 8, 14, 14, 45 * 16, 90 * 16)
        p.drawArc(9, 13, 6, 6, 45 * 16, 90 * 16)
        p.setBrush(QColor(color)); p.drawEllipse(11, 19, 2, 2)
    elif kind == "eye":
        p.drawEllipse(3, 7, 18, 10); p.drawEllipse(9, 9, 6, 6)
    elif kind == "copy":
        p.drawRoundedRect(8, 7, 12, 14, 2, 2)
        p.drawLine(15, 3, 5, 3); p.drawLine(5, 3, 5, 16)
    elif kind == "refresh":
        p.drawArc(4, 4, 16, 16, 40 * 16, 280 * 16)
        p.drawLine(20, 4, 20, 10); p.drawLine(20, 10, 14, 10)
    elif kind == "search":
        p.drawEllipse(4, 3, 12, 12); p.drawLine(14, 14, 20, 20)
    elif kind == "lock":
        p.drawRoundedRect(5, 10, 14, 11, 2, 2)
        p.drawArc(8, 2, 8, 14, 0, 180 * 16)
        p.drawLine(12, 15, 12, 17)
    elif kind == "help":
        p.drawEllipse(3, 3, 18, 18)
        p.drawArc(9, 6, 6, 6, -90 * 16, 240 * 16)
        p.drawLine(12, 12, 12, 14); p.drawPoint(12, 18)
    p.end()
    return QIcon(pm)


def label(text: str, size: int = 13, bold: bool = False, name: str = "", wrap: bool = False) -> QLabel:
    w = QLabel(text)
    w.setStyleSheet("font-size: " + str(size) + "px; font-weight: " + ("700" if bold else "400") + ";")
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    w.setTextFormat(Qt.TextFormat.PlainText)
    return w


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(); frame.setObjectName("card")
    layout = QVBoxLayout(frame); layout.setContentsMargins(22, 22, 22, 22); layout.setSpacing(14)
    return frame, layout


class TaskSignals(QObject):
    done = Signal(object, object)


class Task(QRunnable):
    def __init__(self, fn: Callable):
        super().__init__(); self.fn = fn; self.signals = TaskSignals()

    def run(self) -> None:
        try:
            self.signals.done.emit(self.fn(), None)
        except WifiError as error:
            self.signals.done.emit(None, error)
        except Exception:
            # Never send backend stdout, raw OS responses, or secret-bearing tracebacks to UI/logs.
            self.signals.done.emit(None, WifiError("unexpected", "Proses belum berhasil. Coba lagi atau buka pengaturan sistem."))


class SecretField(QLineEdit):
    copy_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setDragEnabled(False)
        self.setInputMethodHints(Qt.InputMethodHint.ImhSensitiveData | Qt.InputMethodHint.ImhNoPredictiveText)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_requested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class ManualDialog(QDialog):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setWindowTitle("Nama jaringan Wi-Fi"); self.setMinimumWidth(430)
        layout = QVBoxLayout(self); layout.setContentsMargins(26, 26, 26, 26); layout.setSpacing(16)
        layout.addWidget(label("Masukkan nama Wi-Fi", 22, True))
        layout.addWidget(label("Gunakan nama jaringan persis seperti yang tersimpan di Mac, termasuk huruf besar dan spasi.", name="muted", wrap=True))
        self.input = QLineEdit(); self.input.setPlaceholderText("Nama jaringan / SSID"); self.input.setAccessibleName("Nama jaringan Wi-Fi tersimpan")
        layout.addWidget(self.input)
        self.error = label("", name="error", wrap=True); self.error.hide(); layout.addWidget(self.error)
        actions = QHBoxLayout(); actions.addStretch()
        cancel = QPushButton("Batal"); cancel.clicked.connect(self.reject); actions.addWidget(cancel)
        self.submit = QPushButton("Pilih jaringan"); self.submit.setObjectName("primary"); actions.addWidget(self.submit)
        layout.addLayout(actions)
        self.input.returnPressed.connect(self.submit.click)


class MainWindow(QMainWindow):
    SECRET_SECONDS = 30
    CLIPBOARD_SECONDS = 30

    def __init__(self, backend=None):
        super().__init__()
        self.backend = backend or backend_for_platform()
        self.is_demo = isinstance(self.backend, DemoBackend)
        self._profiles = []
        self._selected = None
        self._secret = ""
        self._remaining = 0
        self._generation = 0
        self._list_generation = 0
        self._tasks = {}
        self._listing = False
        self._revealing = False
        self._closed = False
        self._clipboard_token = ""
        self.pool = QThreadPool(self)
        self.setWindowTitle("SONIC WiFi Finder" + (" — Demo" if self.is_demo else ""))
        self.setWindowIcon(QIcon(str(asset_path("app-icon.png"))))
        self.resize(1040, 740); self.setMinimumSize(880, 650)
        self.setStyleSheet(STYLE)
        self._build()
        self.secret_timer = QTimer(self); self.secret_timer.setInterval(1000); self.secret_timer.timeout.connect(self._tick_secret)
        self.clipboard_timer = QTimer(self); self.clipboard_timer.setSingleShot(True); self.clipboard_timer.timeout.connect(self._clear_own_clipboard)
        self.refresh_shortcut = QShortcut(QKeySequence("Ctrl+R"), self); self.refresh_shortcut.activated.connect(self.refresh)
        self.hide_shortcut = QShortcut(QKeySequence("Escape"), self); self.hide_shortcut.activated.connect(self.hide_secret)
        QApplication.instance().applicationStateChanged.connect(self._application_state_changed)
        QTimer.singleShot(0, self.refresh)

    def _build(self) -> None:
        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(30, 24, 30, 18); outer.setSpacing(20)
        header = QHBoxLayout(); header.setSpacing(12)
        app_icon = QLabel(); app_icon.setPixmap(QPixmap(str(asset_path("app-icon.png"))).scaled(46, 46, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)); app_icon.setFixedSize(46, 46)
        header.addWidget(app_icon)
        brand = QVBoxLayout(); brand.setSpacing(1); brand.addWidget(label("S O N I C", 11, True, "eyebrow")); brand.addWidget(label("WiFi Finder", 20, True)); header.addLayout(brand)
        header.addStretch()
        self.platform_badge = label("DEMO · DATA CONTOH" if self.is_demo else self.backend.platform_name, 11, name="pill")
        header.addWidget(self.platform_badge)
        help_btn = QPushButton("Panduan"); help_btn.setObjectName("quiet"); help_btn.setIcon(icon("help")); help_btn.clicked.connect(self.show_help); header.addWidget(help_btn)
        outer.addLayout(header)

        hero = QVBoxLayout(); hero.setSpacing(6)
        hero.addWidget(label("Temukan kembali password Wi-Fi.", 27, True))
        hero.addWidget(label("Pilih jaringan yang tersimpan di perangkat ini, lalu tampilkan passwordnya.", 13, name="muted", wrap=True))
        outer.addLayout(hero)

        body = QHBoxLayout(); body.setSpacing(18)
        left, left_layout = card(); left.setMinimumWidth(288); left.setMaximumWidth(360)
        list_header = QHBoxLayout(); list_header.addWidget(label("Jaringan tersimpan", 15, True)); list_header.addStretch()
        self.refresh_btn = QPushButton(); self.refresh_btn.setIcon(icon("refresh")); self.refresh_btn.setFixedSize(34, 34); self.refresh_btn.setObjectName("quiet"); self.refresh_btn.setToolTip("Muat ulang daftar (Ctrl+R)"); self.refresh_btn.setAccessibleName("Muat ulang daftar jaringan"); self.refresh_btn.clicked.connect(self.refresh); list_header.addWidget(self.refresh_btn)
        left_layout.addLayout(list_header)
        self.search = QLineEdit(); self.search.setPlaceholderText("Cari nama jaringan"); self.search.setAccessibleName("Cari jaringan tersimpan"); self.search.addAction(icon("search", "#7e92af"), QLineEdit.ActionPosition.LeadingPosition); self.search.textChanged.connect(self._filter)
        left_layout.addWidget(self.search)
        self.networks = QListWidget(); self.networks.setSpacing(3); self.networks.setIconSize(QSize(24, 24)); self.networks.setAccessibleName("Daftar jaringan Wi-Fi tersimpan"); self.networks.currentItemChanged.connect(self._select_item)
        left_layout.addWidget(self.networks, 1)
        self.empty_label = label("Memuat jaringan…", name="muted", wrap=True); self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter); left_layout.addWidget(self.empty_label)
        self.count_label = label("Memuat daftar…", 11, name="muted"); left_layout.addWidget(self.count_label)
        self.manual_btn = QPushButton("Masukkan nama Wi-Fi"); self.manual_btn.setObjectName("quiet"); self.manual_btn.setVisible(bool(self.backend.supports_manual)); self.manual_btn.clicked.connect(self._manual); left_layout.addWidget(self.manual_btn)
        body.addWidget(left, 1)

        right = QVBoxLayout(); right.setSpacing(14)
        detail, detail_layout = card()
        detail_header = QHBoxLayout()
        network_icon = QLabel(); network_icon.setPixmap(icon("wifi", "#76aaff", 38).pixmap(38, 38)); network_icon.setFixedSize(44, 44); detail_header.addWidget(network_icon)
        titles = QVBoxLayout(); titles.setSpacing(4); titles.addWidget(label("JARINGAN DIPILIH", 11, True, "eyebrow"))
        self.network_name = label("Pilih jaringan Wi-Fi", 21, True, wrap=True); self.network_name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); titles.addWidget(self.network_name); detail_header.addLayout(titles, 1)
        detail_layout.addLayout(detail_header)
        self.network_meta = label("Jaringan yang pernah disimpan akan muncul di sebelah kiri.", 12, name="muted", wrap=True); detail_layout.addWidget(self.network_meta)
        detail_layout.addSpacing(4)
        detail_layout.addWidget(label("Password jaringan", 13, True))
        password_row = QHBoxLayout(); password_row.setSpacing(8)
        self.password = SecretField(); self.password.setReadOnly(True); self.password.setPlaceholderText("Belum ditampilkan"); self.password.setAccessibleName("Password jaringan dipilih"); self.password.setMinimumHeight(48)
        self.password.setStyleSheet("font-family: 'Consolas', 'Menlo', monospace; font-size: 16px;")
        self.password.copy_requested.connect(self.copy_secret)
        password_row.addWidget(self.password, 1)
        self.copy_btn = QPushButton(); self.copy_btn.setIcon(icon("copy")); self.copy_btn.setFixedSize(48, 48); self.copy_btn.setToolTip("Salin password (clipboard dibersihkan setelah 30 detik)"); self.copy_btn.setAccessibleName("Salin password"); self.copy_btn.setEnabled(False); self.copy_btn.clicked.connect(self.copy_secret); password_row.addWidget(self.copy_btn)
        detail_layout.addLayout(password_row)
        self.reveal_btn = QPushButton("Tampilkan password"); self.reveal_btn.setObjectName("primary"); self.reveal_btn.setIcon(icon("eye", "#ffffff")); self.reveal_btn.setMinimumHeight(46); self.reveal_btn.setEnabled(False); self.reveal_btn.clicked.connect(self.reveal_or_hide); detail_layout.addWidget(self.reveal_btn)
        self.reveal_hint = label("Sistem mungkin meminta izin atau autentikasi Anda.", 11, name="muted", wrap=True); detail_layout.addWidget(self.reveal_hint)
        self.notice = label("", name="notice", wrap=True); self.notice.hide(); detail_layout.addWidget(self.notice)
        detail_layout.addStretch(1)
        privacy = QHBoxLayout(); lock = QLabel(); lock.setPixmap(icon("lock", "#8199ba", 16).pixmap(16, 16)); privacy.addWidget(lock)
        privacy.addWidget(label("Diproses lokal · Password tidak disimpan oleh aplikasi", 11, name="muted", wrap=True), 1); detail_layout.addLayout(privacy)
        right.addWidget(detail, 1)

        support, support_layout = card(); support_layout.setContentsMargins(20, 16, 20, 16); support_layout.setSpacing(8)
        support_layout.addWidget(label("Jaringan belum muncul?", 13, True))
        support_layout.addWidget(label("Muat ulang daftar atau lihat jaringan tersimpan melalui pengaturan sistem.", 12, name="muted", wrap=True))
        support_actions = QHBoxLayout()
        self.settings_btn = QPushButton("Buka pengaturan Wi-Fi"); self.settings_btn.setObjectName("quiet"); self.settings_btn.clicked.connect(self.open_settings); self.settings_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed); support_actions.addWidget(self.settings_btn)
        if self.backend.supports_manual and hasattr(self.backend, "open_password_manager"):
            passwords_btn = QPushButton("Buka app Passwords"); passwords_btn.setObjectName("quiet"); passwords_btn.clicked.connect(self.open_password_manager); support_actions.addWidget(passwords_btn)
        support_actions.addStretch(); support_layout.addLayout(support_actions)
        right.addWidget(support)
        body.addLayout(right, 2); outer.addLayout(body, 1)
        footer = QHBoxLayout(); self.status = label("Menyiapkan aplikasi…", 11, name="muted", wrap=True); footer.addWidget(self.status, 1)
        footer.addWidget(label("v" + __version__, 11, name="muted")); outer.addLayout(footer)
        QWidget.setTabOrder(self.search, self.networks); QWidget.setTabOrder(self.networks, self.reveal_btn); QWidget.setTabOrder(self.reveal_btn, self.copy_btn); QWidget.setTabOrder(self.copy_btn, self.settings_btn)

    def _run(self, fn: Callable, callback: Callable) -> None:
        task = Task(fn); key = id(task); self._tasks[key] = task
        def finish(value, error):
            self._tasks.pop(key, None)
            if not self._closed:
                callback(value, error)
        task.signals.done.connect(finish, Qt.ConnectionType.QueuedConnection)
        self.pool.start(task)

    def refresh(self) -> None:
        if self._listing or self._revealing:
            return
        self.hide_secret(); self._list_generation += 1; generation = self._list_generation
        self._listing = True; self.refresh_btn.setEnabled(False); self.networks.setEnabled(False); self.reveal_btn.setEnabled(False)
        self.manual_btn.setEnabled(False)
        self.status.setText("Membaca daftar jaringan tersimpan…")
        self._set_notice("")
        def loaded(profiles, error):
            if generation != self._list_generation:
                return
            self._listing = False; self.refresh_btn.setEnabled(True); self.networks.setEnabled(True)
            self.manual_btn.setEnabled(True)
            self._profiles = profiles or []
            self._filter()
            if error:
                self._set_notice(str(error), True); self.status.setText("Daftar belum tersedia. Lihat petunjuk di panel kanan.")
            else:
                self.status.setText("Mode demo · Jaringan dan password pada layar adalah data contoh." if self.is_demo else "Siap · Pilih satu jaringan untuk melihat detailnya.")
        self._run(self.backend.list_profiles, loaded)

    def _filter(self, _text=None) -> None:
        previous = self._selected.id if self._selected else None
        query = self.search.text().casefold()
        self.networks.blockSignals(True); self.networks.clear()
        chosen = None
        shown = [p for p in self._profiles if query in p.name.casefold()]
        for profile in shown:
            item = QListWidgetItem(icon("wifi"), profile.name)
            item.setData(Qt.ItemDataRole.UserRole, profile)
            item.setToolTip(profile.name + "\n" + (profile.interface or profile.source or "Jaringan tersimpan"))
            item.setSizeHint(QSize(200, 54)); self.networks.addItem(item)
            if profile.id == previous:
                chosen = item
        self.networks.blockSignals(False)
        if chosen:
            self.networks.setCurrentItem(chosen)
        elif self.networks.count():
            self.networks.setCurrentRow(0)
        else:
            self._select_item(None)
        self.empty_label.setText("Nama jaringan tidak ditemukan." if query else "Belum ada jaringan tersimpan yang dapat dibaca.")
        self.empty_label.setVisible(not shown)
        manual_count = sum(p.security == "Belum diperiksa" for p in self._profiles)
        summary = str(len(self._profiles) - manual_count) + " jaringan tersimpan"
        if manual_count:
            summary += " · " + str(manual_count) + " manual"
        self.count_label.setText((str(len(shown)) + " hasil · " if query else "") + summary)

    def _select_item(self, item, _previous=None) -> None:
        self.hide_secret(); self._generation += 1
        self._selected = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.reveal_btn.setEnabled(bool(self._selected) and not self._revealing and not self._listing)
        self._set_notice("")
        if not self._selected:
            self.network_name.setText("Pilih jaringan Wi-Fi")
            self.network_meta.setText("Pilih jaringan dari daftar atau buka pengaturan sistem.")
        else:
            self.network_name.setText(self._selected.name)
            self.network_meta.setText(" · ".join(x for x in [self._selected.security, self._selected.source or self.backend.platform_name] if x))

    def _set_notice(self, text: str, error: bool = False) -> None:
        self.notice.setObjectName("error" if error else "notice")
        self.notice.style().unpolish(self.notice); self.notice.style().polish(self.notice)
        self.notice.setText(text); self.notice.setVisible(bool(text))

    def reveal_or_hide(self) -> None:
        if self._secret:
            self.hide_secret(); return
        if not self._selected or self._revealing or self._listing:
            return
        self._revealing = True; self._generation += 1; generation = self._generation; profile = self._selected
        self.reveal_btn.setEnabled(False); self.reveal_btn.setText("Menunggu izin sistem…")
        self.networks.setEnabled(False); self.refresh_btn.setEnabled(False); self.search.setEnabled(False); self.manual_btn.setEnabled(False)
        self._set_notice("Jika dialog Windows atau Keychain muncul, selesaikan di perangkat Anda.")
        self.status.setText("Meminta password untuk jaringan yang dipilih…")
        def revealed(secret, error):
            self._revealing = False
            self.networks.setEnabled(True); self.refresh_btn.setEnabled(True); self.search.setEnabled(True); self.manual_btn.setEnabled(True)
            self.reveal_btn.setText("Tampilkan password"); self.reveal_btn.setEnabled(bool(self._selected))
            if generation != self._generation or not self._selected or profile.id != self._selected.id:
                return
            if error:
                self._set_notice(str(error), True); self.status.setText("Password belum ditampilkan. Ikuti petunjuk pada panel."); return
            if not isinstance(secret, str) or not secret:
                self._set_notice("Tidak ada password yang dapat ditampilkan untuk jaringan ini.", True); return
            def display_if_active():
                if self._closed or generation != self._generation or not self._selected or profile.id != self._selected.id:
                    return
                if QApplication.instance().applicationState() != Qt.ApplicationState.ApplicationActive:
                    self._set_notice("")
                    self.status.setText("Permintaan selesai saat aplikasi tidak aktif. Klik Tampilkan password ketika siap.")
                    return
                self._secret = secret; self.password.setText(secret); self.copy_btn.setEnabled(True)
                self.reveal_btn.setText("Sembunyikan password"); self._remaining = self.SECRET_SECONDS; self.secret_timer.start()
                self.reveal_hint.setText("Disembunyikan otomatis dalam " + str(self._remaining) + " detik.")
                self._set_notice(""); self.status.setText("Password ditampilkan · Salin bila diperlukan, lalu sembunyikan kembali.")
            # Let the native Keychain dialog return focus before displaying sensitive text.
            if QApplication.instance().applicationState() == Qt.ApplicationState.ApplicationActive:
                display_if_active()
            else:
                QTimer.singleShot(250, display_if_active)
        self._run(lambda: self.backend.reveal(profile), revealed)

    def hide_secret(self) -> None:
        self._generation += 1
        if self._revealing:
            cancel = getattr(self.backend, "cancel_pending", None)
            if cancel:
                cancel()
            self.status.setText("Permintaan password dibatalkan.")
        self._secret = ""; self.password.clear(); self.copy_btn.setEnabled(False)
        if hasattr(self, "secret_timer"):
            self.secret_timer.stop()
        self.reveal_btn.setText("Tampilkan password"); self.reveal_hint.setText("Sistem mungkin meminta izin atau autentikasi Anda.")

    def _tick_secret(self) -> None:
        self._remaining -= 1
        if self._remaining <= 0:
            self.hide_secret(); self.status.setText("Password disembunyikan otomatis. Anda dapat menampilkannya kembali.")
        else:
            self.reveal_hint.setText("Disembunyikan otomatis dalam " + str(self._remaining) + " detik.")

    def copy_secret(self) -> None:
        if not self._secret:
            return
        data = QMimeData(); data.setText(self._secret)
        self._clipboard_token = secrets.token_hex(16)
        data.setData("application/x-sonic-wifi-token", QByteArray(self._clipboard_token.encode("ascii")))
        if sys.platform == "win32":
            for value in ("CanIncludeInClipboardHistory", "CanUploadToCloudClipboard"):
                data.setData('application/x-qt-windows-mime;value="' + value + '"', QByteArray(struct.pack("<I", 0)))
        QApplication.clipboard().setMimeData(data)
        self.clipboard_timer.start(self.CLIPBOARD_SECONDS * 1000)
        self.status.setText("Password disalin · Clipboard aplikasi dibersihkan dalam 30 detik.")

    def _clear_own_clipboard(self) -> None:
        clipboard = QApplication.clipboard(); data = clipboard.mimeData()
        if data and self._clipboard_token and bytes(data.data("application/x-sonic-wifi-token")).decode("ascii", "ignore") == self._clipboard_token:
            clipboard.clear()
        self._clipboard_token = ""

    def _application_state_changed(self, state) -> None:
        if state != Qt.ApplicationState.ApplicationActive and self._secret:
            self.hide_secret()

    def _manual(self) -> None:
        if not self.backend.supports_manual or self._revealing:
            return
        dialog = ManualDialog(self)
        def choose():
            try:
                profile = self.backend.manual_profile(dialog.input.text())
            except WifiError as error:
                dialog.error.setText(str(error)); dialog.error.show(); return
            if not any(p.id == profile.id for p in self._profiles):
                self._profiles.append(profile)
            self.search.clear(); self._filter()
            for idx in range(self.networks.count()):
                item = self.networks.item(idx)
                if item.data(Qt.ItemDataRole.UserRole).id == profile.id:
                    self.networks.setCurrentItem(item); break
            dialog.accept()
        dialog.submit.clicked.connect(choose); dialog.exec()

    def open_settings(self) -> None:
        self.hide_secret()
        try:
            self.backend.open_settings()
        except WifiError as error:
            self._set_notice(str(error), True)
        except Exception:
            self._set_notice("Buka pengaturan Wi-Fi melalui menu sistem perangkat Anda.", True)

    def open_password_manager(self) -> None:
        self.hide_secret()
        try:
            self.backend.open_password_manager()
        except WifiError as error:
            self._set_notice(str(error), True)
        except Exception:
            self._set_notice("Buka app Passwords melalui Spotlight di Mac Anda.", True)

    def show_help(self) -> None:
        self.hide_secret()
        dialog = QDialog(self); dialog.setWindowTitle("Panduan SONIC WiFi Finder"); dialog.resize(520, 430)
        layout = QVBoxLayout(dialog); layout.setContentsMargins(28, 26, 28, 24); layout.setSpacing(18)
        layout.addWidget(label("Tiga langkah sederhana", 24, True))
        for title, body in [
            ("1. Pilih jaringan", "Daftar berisi jaringan yang sudah tersimpan di perangkat ini. Gunakan kolom pencarian jika daftarnya panjang."),
            ("2. Tampilkan password", "Selesaikan permintaan izin dari Windows atau macOS. Jika akses tidak diberikan, ikuti petunjuk atau buka pengaturan sistem."),
            ("3. Salin bila diperlukan", "Password disembunyikan setelah 30 detik atau saat berpindah aplikasi. Salinan clipboard dibersihkan setelah 30 detik selama aplikasi tetap berjalan."),
        ]:
            layout.addWidget(label(title, 14, True)); layout.addWidget(label(body, 12, name="muted", wrap=True))
        layout.addWidget(label("Jaringan terbuka tidak memiliki password. Jaringan kantor dengan akun individual mungkin tidak memiliki satu password Wi-Fi yang bisa ditampilkan.", 12, name="muted", wrap=True))
        close = QPushButton("Mengerti"); close.setObjectName("primary"); close.clicked.connect(dialog.accept); layout.addWidget(close)
        dialog.exec()

    def closeEvent(self, event) -> None:
        self._closed = True; self._generation += 1; self._list_generation += 1
        self.hide_secret(); self._clear_own_clipboard()
        cancel = getattr(self.backend, "cancel_pending", None)
        if cancel:
            cancel()
        super().closeEvent(event)

