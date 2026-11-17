"""Focused state/secret-lifecycle checks using synthetic profiles only."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sonic_wifi.backend import DemoBackend, WifiError, WifiProfile
from sonic_wifi.ui import MainWindow


APP = QApplication.instance() or QApplication(["sonic-wifi-ui-tests"])
APP.setQuitOnLastWindowClosed(False)


class CountingBackend(DemoBackend):
    def __init__(self):
        self.list_calls = 0
        self.reveal_calls = []
        self.cancel_calls = 0
        self.list_error = None
        self.reveal_error = None

    def list_profiles(self):
        self.list_calls += 1
        if self.list_error:
            raise self.list_error
        return super().list_profiles()

    def reveal(self, profile):
        self.reveal_calls.append(profile.id)
        if self.reveal_error:
            raise self.reveal_error
        return super().reveal(profile)

    def cancel_pending(self):
        self.cancel_calls += 1


class ControlledWindow(MainWindow):
    """Control completion order without waiting on threads or real OS APIs."""
    def __init__(self, backend):
        self.pending = []
        super().__init__(backend)

    def _run(self, fn, callback):
        self.pending.append((fn, callback))

    def finish_next(self):
        fn, callback = self.pending.pop(0)
        try:
            value, error = fn(), None
        except WifiError as exc:
            value, error = None, exc
        if not self._closed:
            callback(value, error)


class MainWindowTests(unittest.TestCase):
    def setUp(self):
        APP.clipboard().clear()
        self.backend = CountingBackend()
        self.window = ControlledWindow(self.backend)
        self.window.show()
        self.window.activateWindow()
        APP.processEvents()  # Schedules the initial metadata-only refresh.
        self.assertEqual(len(self.window.pending), 1)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()
        APP.clipboard().clear()

    def load(self):
        self.window.finish_next()

    def reveal(self):
        self.window.reveal_or_hide()
        self.window.finish_next()

    def test_launch_loads_metadata_without_reading_any_password(self):
        self.assertEqual(self.backend.reveal_calls, [])
        self.load()
        self.assertEqual(self.backend.list_calls, 1)
        self.assertEqual(self.backend.reveal_calls, [])
        self.assertEqual(self.window.networks.count(), 3)
        self.assertEqual(self.window._selected.name, "SONIC Studio")
        self.assertEqual(self.window.password.text(), "")
        self.assertFalse(self.window.copy_btn.isEnabled())
        self.assertTrue(self.window.reveal_btn.isEnabled())

    def test_search_filters_case_insensitively_and_selects_matching_profile(self):
        self.load()
        self.window.search.setText("rUMaH")
        self.assertEqual(self.window.networks.count(), 1)
        self.assertEqual(self.window._selected.name, "Rumah")
        self.assertEqual(self.window.count_label.text(), "1 hasil · 3 jaringan tersimpan")
        self.assertEqual(self.backend.reveal_calls, [])

    def test_empty_search_result_disables_reveal_and_clears_selection(self):
        self.load()
        self.window.search.setText("does-not-exist")
        self.assertEqual(self.window.networks.count(), 0)
        self.assertIsNone(self.window._selected)
        self.assertFalse(self.window.reveal_btn.isEnabled())
        self.assertIn("tidak ditemukan", self.window.empty_label.text())

    def test_reveal_only_requests_selected_profile_then_hide_clears_ui(self):
        self.load()
        self.window.networks.setCurrentRow(1)
        self.reveal()
        self.assertEqual(self.backend.reveal_calls, ["demo:home"])
        self.assertEqual(self.window.password.text(), "RumahDemo2026!")
        self.assertTrue(self.window.copy_btn.isEnabled())
        self.assertTrue(self.window.secret_timer.isActive())
        self.window.reveal_or_hide()
        self.assertEqual(self.window.password.text(), "")
        self.assertEqual(self.window._secret, "")
        self.assertFalse(self.window.copy_btn.isEnabled())
        self.assertFalse(self.window.secret_timer.isActive())

    def test_selection_change_discards_displayed_secret(self):
        self.load(); self.reveal()
        self.window.networks.setCurrentRow(1)
        self.assertEqual(self.window.password.text(), "")
        self.assertEqual(self.window._secret, "")
        self.assertFalse(self.window.copy_btn.isEnabled())

    def test_timer_hides_password_after_configured_countdown(self):
        self.load(); self.reveal()
        for _ in range(self.window.SECRET_SECONDS):
            self.window._tick_secret()
        self.assertEqual(self.window.password.text(), "")
        self.assertEqual(self.window._secret, "")
        self.assertFalse(self.window.secret_timer.isActive())
        self.assertIn("disembunyikan", self.window.status.text().casefold())

    def test_app_deactivation_hides_an_already_displayed_password(self):
        self.load(); self.reveal()
        self.window._application_state_changed(Qt.ApplicationState.ApplicationInactive)
        self.assertEqual(self.window.password.text(), "")
        self.assertEqual(self.window._secret, "")

    def test_copy_and_timer_clear_only_the_apps_clipboard_entry(self):
        self.load(); self.reveal(); self.window.copy_secret()
        self.assertEqual(APP.clipboard().text(), "SonicDemo2026!")
        self.assertTrue(self.window.clipboard_timer.isActive())
        self.window._clear_own_clipboard()
        self.assertEqual(APP.clipboard().text(), "")

    def test_clipboard_cleanup_preserves_subsequent_user_copy(self):
        self.load(); self.reveal(); self.window.copy_secret()
        APP.clipboard().setText("User copied a different note")
        self.window._clear_own_clipboard()
        self.assertEqual(APP.clipboard().text(), "User copied a different note")

    def test_copy_without_reveal_does_not_overwrite_clipboard(self):
        self.load()
        APP.clipboard().setText("Keep me")
        self.window.copy_secret()
        self.assertEqual(APP.clipboard().text(), "Keep me")

    def test_permission_error_is_visible_without_a_secret(self):
        self.load()
        self.backend.reveal_error = WifiError("permission_denied", "Izin pengujian ditolak.")
        self.reveal()
        self.assertEqual(self.window.notice.text(), "Izin pengujian ditolak.")
        self.assertEqual(self.window.notice.objectName(), "error")
        self.assertEqual(self.window.password.text(), "")
        self.assertFalse(self.window.copy_btn.isEnabled())
        self.assertTrue(self.window.reveal_btn.isEnabled())

    def test_list_failure_has_clear_empty_state_and_no_enabled_reveal(self):
        self.backend.list_error = WifiError("service_unavailable", "Layanan Wi-Fi pengujian tidak berjalan.")
        self.load()
        self.assertEqual(self.window.networks.count(), 0)
        self.assertEqual(self.window.notice.text(), "Layanan Wi-Fi pengujian tidak berjalan.")
        self.assertFalse(self.window.reveal_btn.isEnabled())
        self.assertEqual(self.backend.reveal_calls, [])

    def test_stale_reveal_result_cannot_move_to_another_network(self):
        self.load()
        self.window.reveal_or_hide()
        self.window.networks.setCurrentRow(1)  # Simulates a state change before task completion.
        self.window.finish_next()
        self.assertEqual(self.window._selected.name, "Rumah")
        self.assertEqual(self.window.password.text(), "")
        self.assertEqual(self.window._secret, "")
        self.assertFalse(self.window.copy_btn.isEnabled())

    def test_escape_during_pending_reveal_discards_late_secret(self):
        self.load()
        self.window.reveal_or_hide()
        self.window.hide_secret()  # Escape is connected to this same action.
        self.window.finish_next()
        self.assertEqual(self.window.password.text(), "")
        self.assertEqual(self.window._secret, "")
        self.assertFalse(self.window.copy_btn.isEnabled())
        self.assertGreaterEqual(self.backend.cancel_calls, 1)

    def test_inactive_app_discards_pending_reveal_result(self):
        self.load()
        self.window.reveal_or_hide()
        with patch.object(QApplication, "applicationState", return_value=Qt.ApplicationState.ApplicationInactive):
            self.window.finish_next()
            QTest.qWait(300)
        self.assertEqual(self.window.password.text(), "")
        self.assertEqual(self.window._secret, "")
        self.assertFalse(self.window.copy_btn.isEnabled())
        self.assertIn("tidak aktif", self.window.status.text())

    def test_keyboard_copy_uses_owned_clipboard_route(self):
        self.load(); self.reveal()
        self.window.password.setFocus()
        self.window.password.selectAll()
        QTest.keySequence(self.window.password, QKeySequence(QKeySequence.StandardKey.Copy))
        self.assertEqual(APP.clipboard().text(), "SonicDemo2026!")
        self.assertTrue(APP.clipboard().mimeData().hasFormat("application/x-sonic-wifi-token"))
        self.window._clear_own_clipboard()
        self.assertEqual(APP.clipboard().text(), "")

    def test_manual_entry_is_disabled_until_listing_completes(self):
        self.assertFalse(self.window.manual_btn.isEnabled())
        self.load()
        self.assertTrue(self.window.manual_btn.isEnabled())

    def test_close_clears_own_clipboard_and_requests_backend_cancellation(self):
        self.load(); self.reveal(); self.window.copy_secret()
        self.window.close()
        self.assertEqual(APP.clipboard().text(), "")
        self.assertEqual(self.window.password.text(), "")
        self.assertGreaterEqual(self.backend.cancel_calls, 1)
        self.assertTrue(self.window._closed)


if __name__ == "__main__":
    unittest.main()
