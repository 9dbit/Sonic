"""Offline broker invariants. These tests never launch WinGet or an installer."""
import hashlib
import io
import json
from pathlib import Path

import pytest

from scripts import windows_software as software


PACKAGE = "Vendor.Example"
VERSION = "1.2.3"
INSPECT = {"package_id": PACKAGE, "version": VERSION,
           "accept_source_agreements": True, "accept_package_agreements": True}
SOURCE = {"Arg": software.SOURCE_URL, "Name": "winget", "Type": software.SOURCE_TYPE,
          "Identifier": software.SOURCE_ID, "Data": software.SOURCE_ID}


def inventory_document(packages=(), source=None):
    details = {"Argument": software.SOURCE_URL, "Name": "winget",
               "Type": software.SOURCE_TYPE, "Identifier": software.SOURCE_ID}
    if source:
        details.update(source)
    return {"Sources": [{"SourceDetails": details,
        "Packages": [{"PackageIdentifier": package_id, "Version": version}
                     for package_id, version in packages]}]}


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.inventories = []
        self.source = dict(SOURCE)
        self.install_result = software.ProcessResult(0, "Installer reported success", pid=99)
        self.discovery_result = software.ProcessResult(0, "Publisher: metadata only\nVersion: 1.2.3")
        self.inventory_exit = 0
        self.on_install = None

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        if argv[1:] == ["--version"]:
            return software.ProcessResult(0, "v1.29.380\n")
        if argv[1:3] == ["source", "export"]:
            return software.ProcessResult(0, json.dumps(self.source))
        if argv[1] in {"search", "show"}:
            return self.discovery_result
        if argv[1] == "export":
            if self.inventory_exit == 0:
                value = self.inventories.pop(0) if self.inventories else inventory_document()
                output = Path(argv[argv.index("--output") + 1])
                if value is not None:
                    output.write_text(json.dumps(value), encoding="utf-8")
            return software.ProcessResult(self.inventory_exit, "export output")
        if argv[1] == "install":
            if self.on_install:
                self.on_install(kwargs)
            return self.install_result
        raise AssertionError("Unexpected executable operation")

    @property
    def installs(self):
        return [argv for argv, _ in self.calls if argv[1] == "install"]


@pytest.fixture
def broker(tmp_path, monkeypatch):
    # Offline tests must not install real Windows ACLs for the fictitious token
    # below, including when the same suite runs on a Windows CI worker.
    monkeypatch.setattr(software, "_private_directory",
                        lambda path, sid=None: path.mkdir(parents=True, exist_ok=True))
    runner = FakeRunner()
    obj = software.WindowsSoftwareBroker(tmp_path / "state", runner=runner,
        platform_name="win32", identity_probe=lambda: {"sid": "S-1-5-21-100-200-300-1001",
        "elevated": False}, winget_resolver=lambda: r"C:\WindowsApps\winget.exe",
        discovery_enabled=True, install_enabled=True, clock=lambda: 1000)
    return obj, runner


def inspected_plan(broker):
    result = broker.handle("software.inspect", dict(INSPECT))
    assert result["ok"] is True
    return {"plan": result["plan"], "plan_sha256": result["plan_sha256"]}


@pytest.mark.parametrize("action,payload", [
    ("software.search", {"query": "x; Start-Process cmd", "accept_source_agreements": False}),
    ("software.search", {"query": "--source evil", "accept_source_agreements": False}),
    ("software.search", {"query": "example", "accept_source_agreements": "true"}),
    ("software.search", {"query": "example", "accept_source_agreements": False, "url": "https://evil"}),
    ("software.inspect", {**INSPECT, "package_id": "Vendor.App&whoami"}),
    ("software.inspect", {**INSPECT, "version": "1.0 --override hi"}),
    ("software.inspect", {**INSPECT, "version": "latest"}),
    ("software.inspect", {**INSPECT, "version": "CURRENT"}),
    ("software.inventory", {"accept_source_agreements": True}),
    ("software.uninstall", {"package_id": PACKAGE}),
])
def test_rejects_unstructured_or_unpinned_inputs_before_executing(broker, action, payload):
    obj, runner = broker
    result = obj.handle(action, payload)
    assert result["ok"] is False
    assert runner.calls == []


def test_no_install_at_import_and_both_local_gates_default_off(tmp_path, monkeypatch):
    monkeypatch.delenv("SONIC_SOFTWARE_DISCOVERY_ENABLED", raising=False)
    monkeypatch.delenv("SONIC_SOFTWARE_INSTALL_ENABLED", raising=False)
    runner = FakeRunner()
    obj = software.WindowsSoftwareBroker(tmp_path, runner=runner)
    assert not obj.discovery_enabled and not obj.install_enabled
    assert obj.handle("software.inventory", {})["code"] == "SOFTWARE_DISCOVERY_LOCAL_DISABLED"
    assert not runner.calls


@pytest.mark.parametrize("identity,code", [
    ({"sid": "S-1-5-18", "elevated": True}, "WINGET_CLI_SERVICE_CONTEXT_UNSUPPORTED"),
    ({"sid": "S-1-5-19", "elevated": False}, "WINGET_CLI_SERVICE_CONTEXT_UNSUPPORTED"),
    ({"sid": "S-1-5-21-1", "elevated": True}, "LIMITED_USER_REQUIRED"),
    ({"sid": "S-1-5-21-1"}, "LIMITED_USER_REQUIRED"),
    ({"sid": None, "elevated": False}, "USER_IDENTITY_UNKNOWN"),
])
def test_actual_identity_is_required_and_system_elevation_are_rejected(broker, identity, code):
    obj, runner = broker
    obj.identity_probe = lambda: identity
    assert obj.preflight()["code"] == code
    assert not runner.calls


def test_non_windows_fails_closed(broker):
    obj, runner = broker
    obj.platform_name = "linux"
    assert obj.preflight()["code"] == "WINDOWS_ONLY"
    assert not runner.calls


@pytest.mark.parametrize("field,value", [("Arg", "https://attacker.example/catalog"),
    ("Type", "Microsoft.Rest"), ("Identifier", "lookalike"), ("Name", "other")])
def test_source_name_alone_does_not_authorize_catalog(broker, field, value):
    obj, runner = broker
    runner.source[field] = value
    result = obj.handle("software.search", {"query": "example", "accept_source_agreements": False})
    assert result["code"] == "WINGET_SOURCE_IDENTITY_MISMATCH"
    assert all(argv[1] in {"--version", "source"} for argv, _ in runner.calls)


def test_preflight_is_local_without_accepting_terms_or_creating_files(broker):
    obj, runner = broker
    result = obj.preflight()
    assert result["ok"] and result["limited_user"] and result["source_identity_verified"]
    assert not obj.state_dir.exists()
    assert [argv[1] for argv, _ in runner.calls] == ["--version", "source"]
    assert all("--accept-source-agreements" not in argv for argv, _ in runner.calls)


def test_inspect_keeps_metadata_raw_and_does_not_accept_implicit_terms(broker):
    obj, runner = broker
    args = {**INSPECT, "accept_source_agreements": False, "accept_package_agreements": False}
    result = obj.handle("software.inspect", args)
    assert result["status"] == "inspected" and result["metadata_parsed"] is False
    assert result["evidence"]["kind"] == "winget_show_raw"
    assert result["publisher_signature_verified"] is False
    assert "installed" not in result
    show = next(argv for argv, _ in runner.calls if argv[1] == "show")
    assert "--accept-source-agreements" not in show
    assert "--accept-package-agreements" not in show
    expected_hash = hashlib.sha256(json.dumps(result["plan"], sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    assert result["plan_sha256"] == expected_hash
    assert len(result["plan"]) == 7


def test_install_requires_both_terms_and_locally_inspected_immutable_plan(broker):
    obj, runner = broker
    plan = inspected_plan(obj)
    plan["plan"]["accept_package_agreements"] = False
    assert obj.handle("software.install", plan, task_id="task-1")["code"] == "PLAN_HASH_MISMATCH"
    plan["plan_sha256"] = software.plan_sha256(plan["plan"])
    assert obj.handle("software.install", plan, task_id="task-1")["code"] == "EXPLICIT_AGREEMENT_ACCEPTANCE_REQUIRED"
    plan["plan"]["accept_package_agreements"] = True
    plan["plan"]["version"] = "1.2.4"
    plan["plan_sha256"] = software.plan_sha256(plan["plan"])
    assert obj.handle("software.install", plan, task_id="task-1")["code"] == "LOCAL_INSPECTION_REQUIRED"
    assert not runner.installs


def test_install_gate_and_expired_receipt_prevent_dispatch(broker):
    obj, runner = broker
    plan = inspected_plan(obj)
    obj.install_enabled = False
    assert obj.handle("software.install", plan, task_id="task-1")["code"] == "SOFTWARE_INSTALL_LOCAL_DISABLED"
    obj.install_enabled = True
    obj.clock = lambda: 1000 + software.PLAN_TTL_SECONDS + 1
    assert obj.handle("software.install", plan, task_id="task-1")["code"] == "LOCAL_INSPECTION_EXPIRED"
    assert not runner.installs


def test_install_pins_exact_package_and_verifies_export_not_text(broker):
    obj, runner = broker
    plan = inspected_plan(obj)
    runner.inventories = [inventory_document(), inventory_document([(PACKAGE, VERSION), ("Other.App", "9")])]
    result = obj.handle("software.install", plan, task_id="task-1")
    assert result["ok"] and result["status"] == "succeeded"
    assert result["installed"] == {"package_id": PACKAGE, "version": VERSION, "source": "winget"}
    assert result["evidence"]["packages"] == [result["installed"]]
    assert result["verification"] == {"status": "agent_verified", "method": "winget_export_json"}
    assert result["scope_verified"] is False and "scope" not in result["installed"]
    argv = runner.installs[0]
    assert argv[argv.index("--id") + 1] == PACKAGE
    assert argv[argv.index("--version") + 1] == VERSION
    assert argv[argv.index("--scope") + 1] == "user"
    assert argv[argv.index("--source") + 1] == "winget"
    assert argv[argv.index("--dependency-source") + 1] == "winget"
    for required in ("--no-upgrade", "--exact", "--silent", "--disable-interactivity"):
        assert required in argv
    for forbidden in ("--allow-reboot", "--ignore-security-hash", "--force", "--override", "--custom"):
        assert forbidden not in argv
    assert not list((obj.state_dir / "temporary").iterdir())
    assert not (obj.state_dir / "install.lock").exists()
    again = obj.handle("software.install", plan, task_id="task-1")
    assert again["replayed_result"] and not again["installer_replayed"]
    assert len(runner.installs) == 1


@pytest.mark.parametrize("version", [None, "Unknown", "1.2.4"])
def test_exit_zero_without_exact_version_never_reports_success_or_retries(broker, version):
    obj, runner = broker
    plan = inspected_plan(obj)
    runner.inventories = [inventory_document(), inventory_document([(PACKAGE, version)])]
    result = obj.handle("software.install", plan, task_id="task-1")
    assert result["ok"] is False and result["status"] == "reconciliation_required"
    assert "installed" not in result
    assert (obj.state_dir / "install.lock").exists()
    assert obj.handle("software.install", plan, task_id="task-1")["installer_replayed"] is False
    assert obj.handle("software.install", plan, task_id="new-task")["code"] == "INSTALL_LOCK_REQUIRES_RECONCILIATION"
    assert len(runner.installs) == 1


def test_raw_msi_exit_code_is_not_misread_as_winget_success(broker):
    obj, runner = broker
    plan = inspected_plan(obj)
    runner.install_result = software.ProcessResult(3010, "reboot maybe")
    runner.inventories = [inventory_document(), inventory_document([(PACKAGE, VERSION)])]
    result = obj.handle("software.install", plan, task_id="task-1")
    assert not result["ok"] and result["status"] == "reconciliation_required"


def test_existing_exact_version_is_idempotent_and_different_version_not_upgraded(broker):
    obj, runner = broker
    plan = inspected_plan(obj)
    runner.inventories = [inventory_document([(PACKAGE, VERSION)])]
    result = obj.handle("software.install", plan, task_id="task-1")
    assert result["status"] == "already_installed" and not runner.installs
    runner.inventories = [inventory_document([(PACKAGE, "1.0")])]
    result = obj.handle("software.install", plan, task_id="task-2")
    assert result["code"] == "EXISTING_VERSION_REQUIRES_SEPARATE_ACTION"
    assert not runner.installs


@pytest.mark.parametrize("post_inventory", [None, {"NotSources": []},
    inventory_document([(PACKAGE, VERSION)], {"Identifier": "untrusted"})])
def test_missing_or_wrong_source_inventory_cannot_verify_install(broker, post_inventory):
    obj, runner = broker
    plan = inspected_plan(obj)
    runner.inventories = [inventory_document(), post_inventory]
    result = obj.handle("software.install", plan, task_id="task-1")
    assert not result["ok"] and result["status"] == "reconciliation_required"
    assert (obj.state_dir / "install.lock").exists()


def test_timeout_retains_lock_and_records_uncertain_outcome(broker):
    obj, runner = broker
    plan = inspected_plan(obj)
    runner.install_result = software.ProcessResult(None, timed_out=True, pid=99, process_running=True)
    result = obj.handle("software.install", plan, task_id="task-1")
    assert result["status"] == "reconciliation_required"
    assert result["code"] == "INSTALL_OUTCOME_UNKNOWN"
    assert result["process"]["process_running"] is True
    assert (obj.state_dir / "install.lock").exists()
    again = obj.handle("software.install", plan, task_id="task-1")
    assert not again["installer_replayed"] and len(runner.installs) == 1


def test_lease_loss_before_dispatch_prevents_install(broker):
    obj, runner = broker
    plan = inspected_plan(obj)
    result = obj.handle("software.install", plan, task_id="task-1", cancel_requested=lambda: True)
    assert result["status"] == "cancelled" and not runner.installs


def test_lease_loss_after_dispatch_does_not_skip_postinstall_verification(broker):
    obj, runner = broker
    plan = inspected_plan(obj)
    cancelled = [False]
    runner.on_install = lambda kwargs: cancelled.__setitem__(0, True)
    runner.install_result = software.ProcessResult(0, cancellation_requested=True, pid=99)
    runner.inventories = [inventory_document(), inventory_document([(PACKAGE, VERSION)])]
    result = obj.handle("software.install", plan, task_id="task-1", cancel_requested=lambda: cancelled[0])
    assert result["ok"] and result["cancellation_requested"] is True
    exports = [(argv, kwargs) for argv, kwargs in runner.calls if argv[1] == "export"]
    assert exports[-1][1]["cancel_requested"] is None
    assert len(runner.installs) == 1


def test_inventory_does_not_accept_terms_and_unknown_version_remains_unknown(broker):
    obj, runner = broker
    runner.inventories = [inventory_document([(PACKAGE, None)])]
    result = obj.handle("software.inventory", {})
    assert result["evidence"]["packages"][0]["version"] is None
    assert result["coverage"] == "winget_catalog_matched_packages_only"
    export = next(argv for argv, _ in runner.calls if argv[1] == "export")
    assert "--accept-source-agreements" not in export


def test_inspection_without_metadata_cannot_create_reviewable_plan(broker):
    obj, runner = broker
    runner.discovery_result = software.ProcessResult(0, " \n ")
    result = obj.handle("software.inspect", dict(INSPECT))
    assert result["code"] == "INSPECTION_METADATA_EMPTY"
    assert "plan" not in result
    assert not list((obj.state_dir / "plans").iterdir())


def test_unicode_raw_output_fits_actual_escaped_http_json_budget(broker):
    obj, runner = broker
    runner.discovery_result = software.ProcessResult(0, "🙂漢" * 12000, "🙂漢" * 12000)
    result = obj.handle("software.inspect", dict(INSPECT))
    assert result["status"] == "inspected" and result["evidence"]["truncated"]
    assert len(json.dumps(result, separators=(",", ":")).encode("utf-8")) <= 30000


def test_large_inventory_is_bounded_with_count_and_explicit_truncation(broker):
    obj, runner = broker
    entries = [("Vendor." + str(i) + "a" * 100, "🙂" * 100) for i in range(800)]
    runner.inventories = [inventory_document(entries)]
    result = obj.handle("software.inventory", {})
    assert result["ok"] is True
    assert result["evidence"]["matched_package_count"] == 800
    assert result["evidence"]["truncated"] is True
    assert len(result["evidence"]["packages"]) < 800
    assert len(json.dumps(result, separators=(",", ":")).encode("utf-8")) <= 30000


def test_targeted_install_does_not_include_unrelated_inventory_warnings(broker):
    obj, runner = broker
    plan = inspected_plan(obj)
    runner.inventories = [inventory_document(), inventory_document([(PACKAGE, VERSION)])]
    result = obj.handle("software.install", plan, task_id="task-1")
    assert result["ok"]
    # Installer output is relevant. Export's stdout may name unrelated software
    # and never enters the targeted installation receipt.
    assert "export output" not in json.dumps(result)
    assert len(json.dumps(result, separators=(",", ":")).encode("utf-8")) <= 30000


def test_secret_environment_is_not_inherited_by_vendor_installers(monkeypatch):
    monkeypatch.setenv("SONIC_DEVICE_TOKEN", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("SOMETHING_ELSE_SECRET", "secret")
    monkeypatch.setenv("PATH", "C:/Windows")
    assert software._safe_env().get("PATH") == "C:/Windows"
    assert not any("secret" == value for value in software._safe_env().values())


class FakeProcess:
    def __init__(self):
        self.pid = 123
        self.stdout = io.BytesIO(b"bounded output")
        self.stderr = io.BytesIO()
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -1

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def test_process_timeout_never_kills_mutating_installer(monkeypatch):
    proc = FakeProcess()
    calls = []
    monkeypatch.setattr(software.subprocess, "Popen", lambda argv, **kwargs:
                        calls.append((argv, kwargs)) or proc)
    times = iter((0.0, 2.0))
    monkeypatch.setattr(software.time, "monotonic", lambda: next(times))
    result = software.run_process(["winget.exe", "install"], timeout_seconds=1, mutation=True)
    assert result.timed_out and result.process_running
    assert not proc.terminated and not proc.killed
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["stdin"] == software.subprocess.DEVNULL


def test_process_cancel_before_spawn_has_no_side_effect(monkeypatch):
    monkeypatch.setattr(software.subprocess, "Popen", lambda *args, **kwargs:
                        (_ for _ in ()).throw(AssertionError("Must not spawn")))
    result = software.run_process(["winget.exe", "install"], timeout_seconds=1,
                                  mutation=True, cancel_requested=lambda: True)
    assert result.cancelled and result.pid is None


def test_read_only_timeout_can_terminate_only_its_own_process(monkeypatch):
    proc = FakeProcess()
    monkeypatch.setattr(software.subprocess, "Popen", lambda *args, **kwargs: proc)
    times = iter((0.0, 2.0))
    monkeypatch.setattr(software.time, "monotonic", lambda: next(times))
    result = software.run_process(["winget.exe", "search"], timeout_seconds=1)
    assert result.timed_out and proc.terminated
    assert not proc.killed and not result.process_running
