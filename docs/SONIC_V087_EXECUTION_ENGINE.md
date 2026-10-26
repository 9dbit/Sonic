# SONIC V0.8.7 execution engine

Continues staging source `25466423a973555381dd673041c9d11125050396` (V0.8.6).

## Resulting behavior

Voice and text PC requests use one durable execution path. A recognized voice
action is passed as validated structured data, together with its original
transcript; it is no longer regenerated as prose and parsed a second time.
Curly-quoted folder names retain their exact intended name and Desktop scope.

The execution engine selects only a live, independently authorized adapter.
Windows Native is implemented using the existing outbound-only companion.
RDC, Google Drive and Notepad remain explicitly unconnected/not-ready; no new
connector credentials or execution permissions are inferred from ChatGPT.

## Durable dispatch and recovery

- New clients send `request_id` to `POST /api/chat`; older clients remain supported.
- The additive `execution_tasks_v087` table binds a hashed input identity to
  exactly one `OperatorRequest` and its chat-operation receipt in one transaction.
- A unique constraint prevents concurrent HTTP retries from queueing duplicate
  operations. Reusing an accepted identity with changed text returns HTTP 409.
- Lost responses recover the original task ID, including a worker failure after
  queue commit but before its response was saved. No automatic re-execution of
  completed, failed, cancelled or expired tasks occurs.
- Voice retries reuse the same provider item identity. Failed/uncertain dispatch
  cannot remain labelled processing forever or fall through to a model-generated
  PC success response.
- Pending/running tasks resume their browser monitoring after refresh within
  the same owner login. Task metadata is scoped to that login.

## States, evidence and control

`awaiting_approval -> queued -> running -> completed / failed`

`cancelled` and `expired` are terminal execution states. A late device result
does not revive them. Submission and approval are distinguished from execution.

Folder completion requires a matching authenticated companion receipt with
`exists=true`, a boolean `created`, a valid absolute Windows path, and the
requested name/scope or exact workspace-relative destination. A successful flag
with missing or mismatching evidence is marked failed and cannot produce a
successful-folder message. The compatible companion performs filesystem checks
locally. This is **agent-verified evidence, not independent remote readback**.
PowerShell remains **agent-reported**; its exit does not prove every application
side effect independently.

Chat buttons carry the exact proposal ID. A stale button cannot authorize a
newer proposal. Speech alone still does not approve powerful commands. Existing
capability, owner session, CSRF, command digest, lease and Limited-user controls
remain in force. Stale capability advertisements are not callable.

Setup contains task activity and a Stop All PC Tasks control; active chat cards
also provide individual cancellation. Stop cancels this login's queued and
leased operations. Cooperating long-running commands observe cancellation at
their next lease check. An already-started instantaneous operation may finish;
cancellation is not a rollback and does not undo earlier device changes.

## API

- `GET /api/engine/tasks`: recent tasks belonging to the current login.
- `GET /api/engine/tasks/{id}`: phase, adapter, channel, expiry and evidence.
- `POST /api/engine/stop`: CSRF-protected cancellation of this login's PC work.
- Existing operator status endpoints also expose the corresponding task.
- Engine-run status follows the actual device operation rather than HTTP dispatch.

The new ledger contains hashed request identities, operational replies and
bounded verification metadata. Original messages remain in the existing private
chat history. Credentials and transcripts are not added to execution audit runs.

## Validation

- Local Python suite: 283 passed, 2 skipped (disposable PostgreSQL tests require CI).
- JavaScript lifecycle/voice/motion suite: 23 passed.
- Real local HTTP and disposable database, desktop and 390x844 mobile browser:
  lost response replay, one queued job, wrong-target rejection, refresh recovery,
  matching agent evidence, stale approval rejection and zero page errors.
- Existing desktop/mobile voice-dispatch and inline-approval regression passed.
- A PostgreSQL concurrency test runs in the existing isolated CI PostgreSQL
  service; it never uses the staging database.
- Browser/agent fixtures are synthetic. They are not live microphone, physical
  iPhone or actual Windows filesystem acceptance evidence.

## Deployment and next work

Staging deployment and actual Windows acceptance are recorded separately after
release. No companion reinstall, credential rotation, new Windows privileges or
production changes are needed for this backward-compatible server release.

Next milestones are a SONIC-owned RDC connection handshake, Google OAuth, a
verified interactive Notepad workflow, and bounded multi-step task planning.
Those connectors and multi-step workflows are not claimed implemented here.

Rollback: point only Railway SONIC / staging / sonic-web back to
`feature/sonic-integration-brain-v086-20261026` at the base SHA above. The additive
task table may remain; existing chat, memory, owner and companion data are unchanged.
