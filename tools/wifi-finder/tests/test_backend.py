import subprocess
import threading
import unittest
from unittest.mock import Mock, patch

from sonic_wifi.backend import (
    DemoBackend, MacOSBackend, UnsupportedBackend, WifiError, WifiProfile,
    WindowsBackend, _GUID, _keychain_error, _preferred_names, _profile_password,
    _run_command, _wifi_devices, backend_for_platform,
)


def profile_xml(auth="WPA2PSK", encryption="AES", protected="false", key="Test&amp;Key", onex="false"):
    return f'''<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <MSM><security><authEncryption><authentication>{auth}</authentication>
    <encryption>{encryption}</encryption><useOneX>{onex}</useOneX></authEncryption>
    <sharedKey><protected>{protected}</protected><keyMaterial>{key}</keyMaterial></sharedKey>
    </security></MSM></WLANProfile>'''


class WindowsProfileTests(unittest.TestCase):
    def test_plaintext_preserves_spaces_and_xml_characters(self):
        self.assertEqual(_profile_password(profile_xml(key="  Test&amp;Key  ")), "  Test&Key  ")

    def test_encrypted_blob_never_displayed_as_password(self):
        with self.assertRaises(WifiError) as cm:
            _profile_password(profile_xml(protected="true", key="01000000ABCDEF"))
        self.assertEqual(cm.exception.code, "permission_denied")
        self.assertNotIn("ABCDEF", str(cm.exception))

    def test_missing_protection_flag_not_treated_as_plaintext(self):
        with self.assertRaises(WifiError) as cm:
            _profile_password(profile_xml(protected=""))
        self.assertEqual(cm.exception.code, "not_found")

    def test_enterprise_and_open_are_different_outcomes(self):
        for text, expected in [
            (profile_xml(auth="WPA2", onex="true"), "enterprise"),
            (profile_xml(auth="open", encryption="none"), "no_password"),
            (profile_xml(auth="OWE", encryption="AES"), "no_password"),
        ]:
            with self.subTest(expected=expected), self.assertRaises(WifiError) as cm:
                _profile_password(text)
            self.assertEqual(cm.exception.code, expected)

    def test_wep_open_authentication_still_has_shared_key(self):
        self.assertEqual(_profile_password(profile_xml(auth="open", encryption="WEP", key="abcde")), "abcde")

    def test_corrupt_xml_is_friendly(self):
        with self.assertRaises(WifiError) as cm:
            _profile_password("<broken")
        self.assertEqual(cm.exception.code, "invalid_profile")

    def test_guid_roundtrip(self):
        guid = "a1d073ee-6169-4528-8eaa-01ee5f33411a"
        self.assertEqual(_GUID.from_text(guid).as_text(), guid)

    def test_invalid_profile_rejected_before_api(self):
        with self.assertRaises(WifiError) as cm:
            WindowsBackend().reveal(WifiProfile("untrusted", "Test"))
        self.assertEqual(cm.exception.code, "invalid_profile")


class MacOSTests(unittest.TestCase):
    def test_wifi_only_hardware_ports(self):
        text = "Hardware Port: Ethernet\nDevice: en0\n\nHardware Port: Wi-Fi\nDevice: en1\nEthernet Address: aa\n"
        self.assertEqual(_wifi_devices(text), ["en1"])

    def test_names_keep_ssid_whitespace_and_punctuation(self):
        text = "Preferred networks on en0:\n\t Cafe WiFi \n\tStudio:2\n\tStudio:2\n"
        self.assertEqual(_preferred_names(text), [" Cafe WiFi ", "Studio:2"])

    def test_list_never_calls_security_and_deduplicates(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            text = "Hardware Port: Wi-Fi\nDevice: en0\n" if "-listallhardwareports" in args else "Preferred networks on en0:\n\tStudio\n\tStudio\n\tRumah\n"
            return subprocess.CompletedProcess(args, 0, text, "")
        profiles = MacOSBackend(runner).list_profiles()
        self.assertEqual([p.name for p in profiles], ["Rumah", "Studio"])
        self.assertTrue(all(args[0] == "/usr/sbin/networksetup" for args in calls))

    def test_reveal_uses_one_literal_ssid_and_preserves_password_spaces(self):
        calls = []
        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, "  password  \n", "")
        backend = MacOSBackend(runner)
        name = 'Studio;$(echo bad)"'
        profile = backend.manual_profile(name)
        self.assertEqual(backend.reveal(profile), "  password  ")
        self.assertEqual(calls[0][0], ["/usr/bin/security", "find-generic-password", "-D", "AirPort network password", "-a", name, "-w"])
        self.assertEqual(len(calls), 1)

    def test_manual_ssid_byte_limit(self):
        backend = MacOSBackend()
        self.assertEqual(backend.manual_profile(" Name ").name, " Name ")
        for name in ("", "a" * 33, "你" * 11, "bad\x00name"):
            with self.subTest(name=name), self.assertRaises(WifiError):
                backend.manual_profile(name)

    def test_denied_and_missing_keychain_are_friendly(self):
        for code, stderr, expected in [(44, "item could not be found", "not_found"), (128, "User canceled", "permission_denied"), (36, "User interaction is not allowed", "permission_denied")]:
            result = subprocess.CompletedProcess([], code, "", stderr)
            error = _keychain_error(result)
            self.assertEqual(error.code, expected)
            self.assertNotIn(stderr, str(error))

    def test_missing_profile_does_not_return_stdout(self):
        def runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 44, "do-not-show", "item could not be found")
        backend = MacOSBackend(runner)
        with self.assertRaises(WifiError) as cm:
            backend.reveal(backend.manual_profile("Missing"))
        self.assertEqual(cm.exception.code, "not_found")
        self.assertNotIn("do-not-show", str(cm.exception))

    def test_command_timeout_is_sanitized(self):
        with patch("sonic_wifi.backend.subprocess.run", side_effect=subprocess.TimeoutExpired(["security"], 90)):
            with self.assertRaises(WifiError) as cm:
                _run_command(["/usr/bin/security"])
        self.assertEqual(cm.exception.code, "timeout")

    def test_subprocess_never_uses_shell(self):
        with patch("sonic_wifi.backend.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
            _run_command(["/usr/sbin/networksetup", "-listallhardwareports"])
        self.assertIs(run.call_args.kwargs["shell"], False)

    def test_cancel_terminates_only_this_backends_child(self):
        backend = MacOSBackend()
        own_child = Mock()
        own_child.poll.return_value = None
        event = threading.Event()
        backend._pending = {"cancelled": event, "process": own_child}
        backend.cancel_pending()
        self.assertTrue(event.is_set())
        own_child.terminate.assert_called_once_with()
        own_child.kill.assert_not_called()

    def test_cancel_with_no_pending_child_is_noop(self):
        backend = MacOSBackend()
        backend.cancel_pending()

    def test_production_security_helper_releases_process_and_secret_streams(self):
        process = Mock()
        process.communicate.return_value = (" DemoSecret \n", "")
        process.returncode = 0
        process.poll.return_value = 0
        backend = MacOSBackend()
        with patch("sonic_wifi.backend.subprocess.Popen", return_value=process) as popen:
            self.assertEqual(backend.reveal(backend.manual_profile("Studio")), " DemoSecret ")
        self.assertIsNone(backend._pending)
        process.stdout.close.assert_called_once_with()
        process.stderr.close.assert_called_once_with()
        self.assertIs(popen.call_args.kwargs["shell"], False)


class BackendSelectionTests(unittest.TestCase):
    def test_platform_dispatch(self):
        for system, expected in [("Windows", WindowsBackend), ("Darwin", MacOSBackend), ("Linux", UnsupportedBackend)]:
            with patch("sonic_wifi.backend.platform.system", return_value=system):
                self.assertIsInstance(backend_for_platform(), expected)

    def test_demo_is_completely_local(self):
        demo = DemoBackend()
        with patch("sonic_wifi.backend.subprocess.run", side_effect=AssertionError("OS command called")), patch("sonic_wifi.backend._WlanSession", side_effect=AssertionError("WLAN called")):
            profiles = demo.list_profiles()
            self.assertEqual(demo.reveal(profiles[0]), "SonicDemo2026!")
            with self.assertRaises(WifiError) as cm:
                demo.reveal(profiles[2])
        self.assertEqual(cm.exception.code, "no_password")


if __name__ == "__main__":
    unittest.main()
