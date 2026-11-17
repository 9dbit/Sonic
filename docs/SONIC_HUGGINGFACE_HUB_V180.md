# SONIC Hugging Face Hub v1.8.0

## Scope
Native **Devices → Hugging Face Hub** panel. The **Hugging Face Models** shortcut in Devices scrolls to it. Responsive mobile and desktop layout, default black / grey / blue styling.

- Public model search using Hugging Face Hub JSON model API, ordered by popularity and filtered for GGUF.
- Model inspector: repository, author, download count, likes, license, size and filename of available GGUF quantizations.
- Preset searches: Qwen, DeepSeek, Llama, Gemma.
- Open official repository in a new tab.
- Read-only runtime status for TRADEVICEPC (system/gpu available metrics when Companion reports them).
- **Only the existing pinned and locally verified GGUF** can be Start/Stop/Use for Chat, delegated to the preexisting SONIC owner-controlled Local AI Control Center. No arbitrary model download, install, execute, or model replacement.
- Owner-only catalog API routes and no browser tokens. Preview visitors get HTTP 401 and no local control.
- Search/detail requests terminate at a fixed HTTPS `huggingface.co` API, no redirects, no user-provided external URL, hard bounded responses. Model output is treated as untrusted text, never instructions.
- Original local GGUF model remains on disk unchanged. MT5 and the Windows Companion are not modified.
- No automatic request to download or execute 9B models on the Windows GPU.

## Owner APIs
- `GET /api/huggingface/search?q=Qwen3.5%20GGUF&limit=12`
- `GET /api/huggingface/model/{author}/{name}`
- `GET /api/huggingface/local`

## UI
- Open SONIC Owner Portal → Devices → **Hugging Face Models** shortcut (or scroll to the Hub).
- Search a model, pick a card to see its available GGUF variants and repository metadata.
- If it is the pinned DeepSeek-Qwen 9B, review hardware state and use Start / Stop / Use for Chat (subject to existing Companion guards and confirmation).
- For non-pinned models, buttons remain disabled. Model download and installation are not yet implemented, and no arbitrary executable path is accepted.

## Quality gates
```sh
python -m pytest -q tests/test_huggingface_hub_v180.py
python scripts/e2e_huggingface_v180.py
python -m pytest -q tests
node --check web/huggingface-v180.js
```

### Live metadata smoke check
- HF API search for DeepSeek GGUF returned results over HTTPS from TRADEVICEPC.
- HF model details returned 14 GGUF files, including Q4_K_M with 5,780,092,768 bytes.
- The GGUF and runtime executable were found on the machine, but the local model was not started; MetaTrader 5 remained running.
- The current staging source must be deployed and checked separately before calling the panel live.
