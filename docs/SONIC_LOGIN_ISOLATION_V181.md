# SONIC login-isolation hotfix

## Reproduced defect
On the deployed c7cc374 staging build, an unauthenticated /owner visitor on a 390x690 viewport sees the Knowledge toolbar and bottom navigation above the login. The login overlay uses z-index 50; mobile toolbar and sidebar use z-index 100. Mobile initialization reveals Knowledge controls even when the owner has not logged in. The login footer also contains stale VERSION 1.6.0 while /api/health reports 1.7.0.

Previous owner-browser QA verified the login form was visible and the document had no horizontal overflow, but did not assert the application chrome was absent or hit-test the full login card. Its saved screenshot was taken after login on Devices. Therefore those passing tests did not justify claiming the unauthenticated UI was visually acceptable.

## Repair
- Server-rendered locked body state hides the entire application before scripts run. Public preview explicitly removes that state and remains available.
- A dedicated CSS rule ties visibility to the login overlay as well, protecting session expiry and browser restoration. This does not grant or change server permissions.
- A small controller makes application siblings inert and aria-hidden while the login is visible; it restores their prior state after unlocking, observes dynamically inserted siblings, and keeps keyboard focus inside login.
- Login is an opaque, scrollable safe-area-aware screen. The form remains reachable at narrow, landscape and keyboard-height viewports.
- Footer version is rendered from the server version rather than a stale hardcoded string.
- Existing owner QA now explicitly checks hidden application chrome, inert focus state, hit targets and screenshots both before login and after logout.

## Evidence and limits
- The pre-fix screenshot was taken from live staging without owner credentials.
- The post-fix reference screenshot is a real WebKit rendering against a local test server with synthetic credentials, not an image-generation mockup or physical iPhone capture.
- Dedicated browser scenarios cover first load, invalid token, expired session, successful unlock, logout, no JavaScript, session-fetch failure, public preview and passwordless login layout. Portrait 390x690/360x640, landscape 844x390, desktop 1440x900 and a reduced 390x320 keyboard-height simulation are checked.
- This fixes login isolation only. It is not a declaration that every SONIC screen or all physical iPhone interactions are accepted.

## Rollback
Restore the previous pinned staging commit c7cc3744c2c721d692b5ecd05c1cccbaea98b605. This patch changes no credentials, database schema, local model, trading processes or Companion configuration.
