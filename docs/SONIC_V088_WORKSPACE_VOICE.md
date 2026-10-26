# SONIC V0.8.8 Workspace and direct voice

Continues the exact V0.8.7 staging source
`ec407eb4c44384b871b6551f3c05fa6827aaed70` without changing the Windows companion
or its credential. This release targets only SONIC / staging / sonic-web.

## Workspace and Notes

Workspace has folder navigation, breadcrumbs, global filename search, a text
editor, create, rename, move, Trash, restore, dictation and read-aloud controls.
Desktop uses a tree, file list and editor; mobile opens one panel at a time.
Text and Markdown are displayed as literal text, never executed or rendered as
HTML. Notes remain distinct from explicitly saved Memory Vault facts.

The implemented storage root is **SONIC Cloud**, persisted in the existing
database, with no PC or Google Drive synchronization. The PC and Drive roots
are disabled and labelled as not connected to the file manager. Existing PC
chat commands continue through the V0.8.7 execution engine. This release does
not install a companion, route file writes through a shell, provision a bot,
send messages, or claim Windows Notepad is connected.

Storage is additive (`workspace_items_v088`, `workspace_gate_v088`). Owner
authentication protects every read; writes additionally require CSRF. Names
are normalized, unique per parent ignoring case, and reject path separators,
traversal, invalid Windows names and invalid Unicode. Files support `.txt` and
`.md`, up to 100,000 characters; workspace limits are 1,000 items including
Trash, 10 MiB of UTF-8 text, and eight folder levels. A transaction gate
serializes hierarchy, uniqueness, quota and revision checks on PostgreSQL and
SQLite. Creates can replay the same UUID and exact payload without duplicating
an item. Updates, moves, trash and restores require the displayed revision.
Stale edits return 409 and preserve the local draft. Folder trash preserves
its descendants, prevents access to them, and can be restored. A name conflict
prevents restoration instead of overwriting a newer file. There is no permanent
delete in this release.

Drafts stay only in the current page. Refresh/closing warns before losing
unsaved text; server-saved content survives refresh and a new owner login.
Sign-out/session expiry clears workspace data from the UI. No notes or access
tokens are stored in browser localStorage.

## Voice and motion

Single tap preserves the existing 10% preview. A second tap within one second
centers SONIC and immediately invokes microphone capture in that same gesture,
counting that second tap as application consent. There is no second SONIC
confirmation. Browser and OS microphone permission is still required and
cannot be bypassed. An existing voice session is reused, not duplicated.
Audio processing uses the configured Realtime service. Permission/provider
failures stop local media through the existing lifecycle cleanup.

A full black layer fades over the background while SONIC is centered. The
background panels become inert; Mute, Stop, the return button and Escape stay
available. Returning the animation home restores the background and retains
an active voice session, whose visible bar still offers Stop. Resize keeps
SONIC centered; reduced motion removes the fade and travel transition.

Workspace commands use the same authenticated API as its buttons. Examples:
“buka workspace”, “buat folder Proyek”, “buat catatan Rapat”, “cari file Rapat”,
“tambahkan ke catatan …”, “simpan catatan”, “bacakan catatan ini”. Dictated text
first becomes a draft. File deletion opens an exact-item Trash review; “setuju”
or its button submits that captured item/revision. The selected item and parent
are captured at speech start; a changed selection causes clarification instead
of changing a different file. Explicit Desktop/PC/Drive destinations retain
their existing executor route. Provider item de-duplication remains active.

Neural nodes occupy deterministic category islands, with matching group colors,
group labels/counts, lighter cross-group edges, and fewer long labels on mobile.
All knowledge nodes still come from the server; no illustrative facts are added.
Search, filters, focus, tracing and 2D/3D navigation remain available.

## Validation and rollout

- Local Python regression: 293 passed, 3 optional PostgreSQL tests skipped.
- JavaScript geometry and voice lifecycle: 25 passed.
- New desktop/mobile browser workflow uses real HTTP and disposable storage,
  synthetic microphone/WebRTC, and no external provider calls. It covers CRUD,
  conflict preservation, refresh persistence, Trash/restore, voice dispatch,
  changed speech target rejection, one microphone session per double tap,
  permission denial, visible Mute/Stop and no JavaScript errors.
- Existing motion/theme, integration and PC engine browser regressions passed.
- CI runs the additional real PostgreSQL workspace concurrency test in an
  isolated disposable schema, never against the staging database.

Live staging deployment/login/storage acceptance is a separate release check.
Synthetic microphone tests do not establish physical iPhone, real audio
recognition, OS permission or live provider audio acceptance.

Rollback service source to the V0.8.7 SHA above. Leave the additive workspace
tables intact to preserve saved notes. No destructive migration is needed.

## Next milestones

1. A separately verified Windows workspace adapter, bounded to the companion's
   authorized root, with native file result evidence and conflict handling.
2. Calculator, agenda, alarms/reminders and a dedicated SONIC Telegram bot.
3. Google OAuth and scoped Drive actions, then email read/reply with exact
   recipient/content review.
4. Dedicated SONIC WhatsApp Business number and a unified inbox. Personal
   messaging accounts are not assumed authorized by this roadmap.
