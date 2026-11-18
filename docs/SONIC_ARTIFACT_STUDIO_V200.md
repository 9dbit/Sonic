# SONIC Artifact Studio v2.0 (staging)

## What is implemented
- First-class Artifact Studio route in the SONIC owner console.
- Artifacts stored in additive PostgreSQL tables: artifact_items_v200,
  artifact_versions_v200 and artifact_gate_v200. No changes to existing
  workspace items, personal memories, device jobs or model settings.
- Owner-authenticated listing, preview content, create, version, delete.
  Mutations require the existing SONIC owner CSRF token.
- Optimistic version lock (409 on stale update), immutable past versions,
  100 artifact limit, 12 revisions per artifact, 64 MiB total version quota.
- HTML source editor and isolated browser iframe preview, text-only source
  viewer, JPEG/PNG/WebP images, MP3/WAV/OGG/M4A/WebM audio, MP4/WebM video,
  and public HTTPS website links (external tab, no proxy/embedding).
- Chat-generated HTML code blocks can be deliberately moved into a Studio
  draft; a draft is not saved or run until the owner chooses the action.
- Workspace and Devices link to the Studio. Original read-only Windows
  Workspace and PC approval workflows remain unchanged.
- Source export is a browser download; it is NOT host install or deployment.

## Non-capabilities
- Local GGUF is currently text-only. It cannot autonomously execute commands,
  build binary packages, create images, generate music/video, or deploy apps.
- There is no remote shell, unrestricted Python runner, automatic package
  installation, network fetch in artifact HTML, or trusted direct PC access.
- Website preview is a safe HTTPS external open; remote screenshot/iframe
  visual browsing remains a future authenticated capability.
- Media larger than the configured API thresholds needs an object store. No
  user file is automatically uploaded to providers, and no video transcoding
  worker is connected in this release.
- No change to production SONIC or trading processes.

## Threat boundary
HTML preview runs in a sandboxed iframe with allow-scripts only; NO
allow-same-origin, allow-forms, allow-popups, allow-downloads, or top navigation.
The iframe has an opaque origin and restrictive meta CSP: no network,
worker, frames, object/embed, or cross-origin data. The parent CSP restricts
frame sources. Preview carries no SONIC owner credentials. The public guest
and trusted-iPhone preview APIs remain unable to fetch owner artifacts.

Server validates media MIME and binary signature, enforces size quotas, and
rejects local/private HTTP websites. Files are never written to the Windows
Companion by these endpoints.

## QA gates
1. pytest tests/test_artifact_studio_v200.py
2. Playwright Chromium + WebKit, desktop 1440x900 and iPhone 390x844.
3. Check returned media player elements, live HTML arithmetic in opaque frame,
   create/edit/stale revisions, logout data isolation and no JS errors.
4. Run existing SONIC regression workflows before staging.
5. Verify Railway staging terminal SUCCESS, owner API access, and guest 401
   before discussing any production rollout.

## Rollback
Rollback staging to previous known-good deployment. The new artifact database
tables are additive and are not dropped by a code rollback. No destructive
schema cleanup is performed automatically.
