# SONIC Software Manager

Prepared 10 November 2026 (Asia/Jakarta), from Sonic staging source
`aa4e92e81976b5eeda644035d98f474b2c01e2ce`.

## Outcome and release state

This development change adds Windows software discovery, exact-version
inspection, inventory, and an explicitly approved installation through the
existing SONIC native companion. It does not install applications merely by
deploying the web app. Server and local installation gates default to disabled.

At preparation time, SONIC/sonic-web staging was deployed successfully at the
base commit above. TRADEVICEPC was observed online through the authorized RDC
connection, Windows 10 Pro x64, WinGet `v1.29.380`, with the existing SONIC
companion Scheduled Task running at Limited privilege. A direct read-only
WinGet search returned Visual Studio Code package IDs and versions, exit 0.
The WinGet source export matched Microsoft's built-in source URL, type, and ID.
The installed CLI help includes all options used by the proposed installer.
These observations are not acceptance evidence for a live SONIC installation.

The new web/companion code has not been activated on TRADEVICEPC. No application
was selected by the owner for a first installation, so no real installer or
software license acceptance was performed during this work. Cloud staging
deployment and the installed companion remain at their previous versions.

## User flow

1. Say or type `Sonic, cari software Visual Studio Code`, or open
   **Devices > Software Manager** and search a name or keyword.
2. Inspect the exact package ID and version. SONIC displays bounded WinGet
   metadata, including source/publisher/license/installer information when the
   catalog supplies it. Raw metadata is displayed as text and is never executed.
3. Review the source terms and selected package license. Separate agreement
   controls are unchecked by default. Re-inspection binds the exact selections.
4. Review the installation plan and explicitly confirm it once. The plan fixes
   the package, version, source, requested user scope, and agreement choices.
5. The limited Windows companion performs the work and reports the result.
   SONIC labels installation verified only when WinGet export JSON contains the
   exact package ID, version, and source after the attempt.

An `install <name>` chat/voice request starts discovery; it does not guess a
package or accept licenses. `Install Package.Id versi 1.2.3` prepares inspection.
The owner completes the reviewed plan in Software Manager. Natural-language
recommendation across arbitrary websites is not implemented by this change.

## Architecture

The existing owner session/CSRF, request digest, PostgreSQL queue, device lease,
output stream, and receipt endpoints remain the execution path. No additional
inbound Windows listener or ChatGPT connector credential is introduced.

| Component | Responsibility |
| --- | --- |
| Chat/voice parser | Owner-origin software discovery and pinned inspection |
| Software Manager UI | Search, metadata, consent, exact review, result/history |
| `sonic/software.py` | Contracts, feature gates, inspection binding, evidence checks |
| Existing operator/execution service | One reviewed request, lease, stream and receipt |
| `scripts/windows_software.py` | Limited-user WinGet, source check, local plan and journal |
| Windows companion | Fresh heartbeat during long work and receipt delivery |

Installation requires a matching authenticated inspection from the same owner
session/device in the last 30 minutes. A client-written plan alone is rejected.
The broker also requires the same locally persisted inspection. No database
migration is required.

## Scope and operating limits

- WinGet built-in source only, verified by URL/type/identifier, including the
  dependency source. Custom download URLs, raw shell/installer arguments,
  uninstall, upgrade, and machine-wide installation are not supported here.
- The companion must run as the existing limited user. SYSTEM/service identities
  and elevated companion tokens are rejected. No `runas` or privilege increase.
- Install uses an exact ID/version, user scope, silent/noninteractive options,
  and `--no-upgrade`. Hash bypass, force, and reboot permission are not used.
- User scope is a request to the vendor installer, not proof of the actual
  installed scope. EXE installers can still require local UAC or interaction.
- WinGet catalog publisher text is metadata, not independent Authenticode
  verification. WinGet's own installer hash check remains enabled.
- Source/package agreement acceptance is explicit and part of the reviewed plan.
- Each installation has a task journal and exclusive local lock. Unknown outcomes
  prevent automatic replay. The lock is retained when reconciliation is needed.
- Cancel after the installer starts is not rollback. The broker does not force
  kill installer/MSI processes. Late evidence is preserved without reviving a
  cancelled/expired request as normal completion.
- Background heartbeats take new telemetry samples. Bounded progress events
  retain identical payloads across a lost acknowledgment. No invented percentage.
- Receipt delivery retries in the same companion process. After a companion
  process restart, the journal prevents reinstallation but automatic cloud receipt
  recovery is not yet implemented; inspect/reconcile the outcome explicitly.
- Inventory covers packages WinGet can correlate to its catalog. It is not a
  complete registry-level audit of every application or portable executable.

## Controlled activation

Server gates:

```text
SONIC_ENABLE_SOFTWARE_DISCOVERY=true
SONIC_ENABLE_SOFTWARE_INSTALL=true
```

Local companion gates, deliberately independent of server gates:

```text
SONIC_SOFTWARE_DISCOVERY_ENABLED=1
SONIC_SOFTWARE_INSTALL_ENABLED=1
```

`Install-Sonic-Companion.ps1` now offers `-EnableSoftwareDiscovery` and
`-EnableSoftwareInstall`. Installation opt-in requires discovery opt-in.
Run its dry-run/preflight under the intended limited user and preserve existing
PowerShell/window opt-ins deliberately. Do not change Windows task privileges.
Preflight does not advertise candidate software capabilities before the installed
task can execute them. Existing companion files/runner are backed up for rollback.

Before activating installs, select one owner-requested application, review its
exact source/version/license, and perform real staging-owner-to-companion
acceptance. The mock tests do not replace this physical Windows test. Do not
update MetaTrader, trading engines, drivers, or restart the PC as a side effect.

## Validation

Run with a disposable local database and synthetic owner/device credentials:

```text
python -m pytest -q
node --test tests/js/software-manager.test.cjs
python scripts/e2e_software.py
```

The new GitHub workflow also runs broker/companion unit tests on Windows and
parses the PowerShell installer without executing it. Tests cover forged/tampered
plans, wrong versions, prior inspection ownership, stale devices, disabled gates,
missing inventory proof, lost acknowledgments, double clicks, uncertain outcomes,
and late receipts. Browser fixtures never invoke a real software installer.

## Publisher installer extension

Software unavailable through WinGet needs a separate publisher-specific adapter:
official download provenance, verified expected publisher/signature or trusted
hash, pinned installer identity, validated arguments, license/login handling,
and a product-specific installed-version check. This adapter is a next extension,
not part of the current implementation. Source-code repository discovery/build
is likewise separate from application installation.

## Primary documentation

- https://learn.microsoft.com/en-us/windows/package-manager/winget/install
- https://learn.microsoft.com/en-us/windows/package-manager/winget/show
- https://learn.microsoft.com/en-us/windows/package-manager/winget/source
- https://learn.microsoft.com/en-us/windows/package-manager/winget/export
- https://learn.microsoft.com/en-us/windows/package-manager/winget/troubleshooting
