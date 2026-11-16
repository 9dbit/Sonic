# SONIC 1.5.2: Local AI Control Center + Black/Grey/Blue

Staging-only implementation on top of `feat/sonic-trusted-iphone-preview-v151-20261116`.

## User workflow
1. Sign in as SONIC owner on the current Railway staging domain. Public preview guests cannot see/control local AI.
2. Open **Devices → Local AI Control Center** on iPhone Safari, PWA, or desktop.
3. Check fresh Companion heartbeat, RAM and VRAM.
4. Tap **Start AI**. Only the fixed local GGUF model is allowed. Server binds to `127.0.0.1:11435` on TRADEVICEPC.
5. Tap **Use for Chat**, then use SONIC's existing Chat screen. Or choose the Local GGUF model in Settings → Model Router.
6. Tap **Stop AI** to stop only the process started by the current SONIC Companion.

## Existing runtime (already tested in TRADEVICEPC)
- Windows 10 Pro, Intel i3-10100, 16 GB RAM, NVIDIA RTX 2060 6 GB.
- `E:\AI\DeepSeek-V4-Pro-Qwen3.5-9B\model\DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic.Q4_K_M.gguf`
- SHA-256 `b4363b5710a29a03cab49bc10df92ca688f891eba1a63cae912e4d96f3fd7a65`.
- Official llama.cpp Vulkan build b12422, tested `llama-server.exe` with `--n-gpu-layers 12 --ctx-size 1024 --threads 2`.
- No automatic model startup. Existing MetaTrader 5 process is not touched.

## End-to-end architecture
`SONIC owner web/PWA → Railway SONIC FastAPI → authenticated outbound Windows Companion → local llama.cpp → Companion signed receipt → Railway SONIC chat`

- The browser never receives Windows device credentials, file paths to arbitrarily execute, or network URLs.
- Cloud service requires `SONIC_LOCAL_AI_ENABLED=true` in Railway staging and existing owner authentication with CSRF for mutations.
- Windows Companion separately requires owner-created, local `E:\AI\DeepSeek-V4-Pro-Qwen3.5-9B\allow-sonic-local-ai.flag` containing exactly `SONIC_LOCAL_AI_OWNER_APPROVED_V152`.
- Local Companion uses a fixed allowlist for actions: `start`, `stop`, `chat`. A browser cannot specify executable, command, path, model URL, host, port or runtime arguments.
- Chat model **cannot call tools**. It cannot directly control Windows, trades, software, databases, files, or payments.
- Chat transits Railway and is stored in SONIC's existing chat history. This is **local inference**, not a 100% device-local private chat.
- The transient queued prompt is cleared from the queue on lease. Successful results are recorded as SONIC chat messages, consistent with existing SONIC behavior.
- No external model provider is involved when `local` is selected. There is no silent fallback to cloud AI.
- Anonymous preview chat remains limited to its existing explicitly listed cloud providers.

## Resource guard
- 6500 MB free system RAM and 2700 MB free VRAM required to start; otherwise refuse.
- Start command uses fixed local model/engine paths, `--parallel 1`, `--ctx-size 1024`, `--n-gpu-layers 12`, `--threads 2` with below-normal Windows priority.
- Inference capped at 256 generated tokens, no parallel tool calls, bounded single active chat.
- Start/Stop is explicit. Broker stop affects only the subprocess it spawned during the current Companion lifetime; after Companion restart, an orphaned llama process must be inspected/managed locally rather than killing an unverified PID.
- No changes to MT5 processes, Windows shutdown/reboot settings, GPU drivers, broker files, or trading EA.

## Deployment / rollback
1. Commit and test the changes on a new feature branch.
2. Deploy **SONIC / staging / sonic-web** to that branch, inspect Railway deployment and /api/health.
3. Set `SONIC_LOCAL_AI_ENABLED=true` only on that environment once its Companion sidecar is installed.
4. Backup Windows Companion scripts and update only `windows_agent_v05.py` and the new `windows_local_ai_v152.py`. Compile, run one heartbeat, verify MT5 is still running.
5. Ensure owner login is available: if `SONIC_OPEN_PREVIEW=true`, guest UI is intentionally *not* owner-accessible and must not be confused with functional local AI controls.
6. Rollback: set `SONIC_LOCAL_AI_ENABLED=false`, remove local opt-in file, restore prior Companion script backup, then redeploy previous staging commit. Never delete the GGUF model or other data.

## Acceptance
- Owner-only status/control; guests and unauthenticated requests rejected.
- Staging has a black/neutral-grey UI with blue accent; responsive iPhone safe-area navigation.
- One fixed local model, signed receipts, resource guard and non-thinking chat validated.
- All existing provider, voice, WinGet software manager, passkey and Companion tests still pass.
- Physical iPhone owner sign-in and start/stop/chat E2E should be treated as a separate acceptance gate, not fabricated from browser mocks.