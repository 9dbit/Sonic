"""SONIC V1.0 multi-model brain router.

Only owner-selected allowlisted text models. OpenAI Responses and OpenRouter
Chat Completions normalize to the existing bounded SONIC tool-dispatch shape.
No secret, prompt, transcript, reasoning text or raw provider error is logged.
This module does NOT change OpenAI Realtime voice or OpenAI-only vision.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import model_name, setting
from .db import BrainPreference, BrainUsage, utcnow

OPENAI_URL = "https://api.openai.com/v1/responses"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
CATALOG = (
    ("openai", "gpt-4.1-mini", "OpenAI · GPT-4.1 mini"),
    ("openai", "gpt-4.1", "OpenAI · GPT-4.1"),
    ("openrouter", "z-ai/glm-5.3-prime", "OpenRouter · GLM-5.3 Prime"),
    ("openrouter", "z-ai/glm-5.3", "OpenRouter · GLM-5.3"),
)
SAFE_MODEL = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,99}$")
SAFE_CALL = re.compile(r"^[a-zA-Z0-9_-]{1,160}$")
SAFE_TOOL = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,79}$")


@dataclass(frozen=True)
class Selection:
    provider: str
    model: str


def available_models() -> list[dict]:
    """Fixed code-reviewed list, plus trusted server-side model overrides."""
    entries = [dict(provider=p, model=m, label=label) for p, m, label in CATALOG]
    for provider, configured in (
        ("openai", model_name()),
        ("openrouter", setting("SONIC_OPENROUTER_MODEL", "z-ai/glm-5.3-prime")),
    ):
        if SAFE_MODEL.fullmatch(configured) and not any(
            item["provider"] == provider and item["model"] == configured for item in entries
        ):
            entries.append({"provider": provider, "model": configured,
                            "label": f"{provider.title()} · {configured} (server configured)"})
    return entries


def validate_model(provider: str, model: str) -> Selection:
    if not isinstance(provider, str) or not isinstance(model, str) or not any(
        entry["provider"] == provider and entry["model"] == model for entry in available_models()
    ):
        raise HTTPException(422, "Model is not on the SONIC owner allowlist")
    return Selection(provider=provider, model=model)


def configured(provider: str) -> bool:
    return bool(setting("OPENAI_API_KEY" if provider == "openai" else "OPENROUTER_API_KEY")) \
        if provider in ("openai", "openrouter") else False


def selected_model(db: Session) -> Selection:
    row = db.get(BrainPreference, 1)
    if row is not None:
        return validate_model(row.provider, row.model)
    # Existing SONIC deployments default to unchanged OpenAI behavior.
    provider = setting("SONIC_BRAIN_PROVIDER", "openai").lower()
    if provider not in ("openai", "openrouter"):
        raise HTTPException(503, "Invalid SONIC brain provider setting")
    model = (model_name() if provider == "openai"
             else setting("SONIC_OPENROUTER_MODEL", "z-ai/glm-5.3-prime"))
    return validate_model(provider, model)


def choose_model(db: Session, provider: str, model: str) -> Selection:
    selected = validate_model(provider, model)
    if not configured(provider):
        raise HTTPException(409, "Selected provider API key is not configured on the SONIC server")
    row = db.get(BrainPreference, 1)
    if row is None:
        db.add(BrainPreference(id=1, provider=provider, model=model))
    else:
        row.provider, row.model, row.updated_at = provider, model, utcnow()
    db.commit()
    return selected


def public_model_status(db: Session) -> dict:
    selected = selected_model(db)
    options = [{**entry, "key_configured": configured(entry["provider"]),
                "selected": entry["provider"] == selected.provider and entry["model"] == selected.model}
               for entry in available_models()]
    recent = list(db.scalars(select(BrainUsage).order_by(BrainUsage.id.desc()).limit(12)))
    return {"selected": {"provider": selected.provider, "model": selected.model,
                         "key_configured": configured(selected.provider)},
            "models": options,
            "voice": {"provider": "openai", "model": setting("SONIC_REALTIME_MODEL", "gpt-realtime"),
                      "key_configured": configured("openai")},
            "vision": {"provider": "openai", "key_configured": configured("openai")},
            "usage": [{"provider": u.provider, "model": u.model, "status": u.status,
                       "latency_ms": u.latency_ms, "input_tokens": u.input_tokens,
                       "output_tokens": u.output_tokens,
                       "provider_reported_cost_usd": u.reported_cost_usd,
                       "at": u.created_at.isoformat() + "Z"} for u in recent],
            "notice": "Chat model only. Realtime Voice and image analysis remain OpenAI. "
                      "Switching to OpenRouter sends chat context and tool descriptions to that provider. "
                      "No automatic provider fallback or hidden request retries."}


def _int_token(value):
    return value if type(value) is int and 0 <= value <= 100_000_000 else None


def normalized_usage(usage: object) -> dict:
    if not isinstance(usage, dict):
        return {"input_tokens": None, "output_tokens": None, "cost_usd": None}
    cost = usage.get("cost")
    if not isinstance(cost, (int, float)) or isinstance(cost, bool) or not math.isfinite(cost) \
            or not 0 <= cost <= 1000:
        cost = None
    return {"input_tokens": _int_token(usage.get("input_tokens", usage.get("prompt_tokens"))),
            "output_tokens": _int_token(usage.get("output_tokens", usage.get("completion_tokens"))),
            "cost_usd": float(cost) if cost is not None else None}


def record_usage(db: Session, selection: Selection, elapsed_ms: int, status: str,
                 usage: dict | None = None) -> None:
    """Only sanitized counts, selected model and duration; no content or IDs."""
    parsed = normalized_usage(usage)
    db.add(BrainUsage(
        provider=selection.provider, model=selection.model,
        latency_ms=max(0, min(300_000, int(elapsed_ms))),
        status=status if status in ("ok", "error", "incomplete") else "error",
        input_tokens=parsed["input_tokens"],
        output_tokens=parsed["output_tokens"],
        reported_cost_usd=parsed["cost_usd"],
    ))
    db.commit()


def _chat_messages(parts: list[dict], instructions: str) -> list[dict]:
    """Reconstruct Chat Completions tool messages from SONIC Responses trace.

    Must include assistant tool_calls BEFORE corresponding tool messages.
    The existing reply() is still the ONLY executor, with the same allowlist
    and iteration caps independent of the selected model.
    """
    messages = [{"role": "system", "content": instructions}]
    tool_batch: list[dict] = []

    def flush():
        if tool_batch:
            messages.append({"role": "assistant", "tool_calls": list(tool_batch)})
            tool_batch.clear()

    for item in parts:
        if not isinstance(item, dict):
            raise HTTPException(502, "Invalid model conversation format")
        kind = item.get("type")
        if kind == "function_call":
            call_id, name, arguments = item.get("call_id"), item.get("name"), item.get("arguments", "{}")
            if not isinstance(call_id, str) or not SAFE_CALL.fullmatch(call_id) \
                    or not isinstance(name, str) or not SAFE_TOOL.fullmatch(name) \
                    or not isinstance(arguments, str) or len(arguments) > 10_000:
                raise HTTPException(502, "Invalid model tool-call format")
            try:
                parsed = json.loads(arguments)
            except ValueError:
                raise HTTPException(502, "Invalid model tool arguments") from None
            if not isinstance(parsed, dict):
                raise HTTPException(502, "Invalid model tool arguments")
            tool_batch.append({"id": call_id, "type": "function",
                               "function": {"name": name, "arguments": arguments}})
        elif kind == "function_call_output":
            flush()
            call_id = item.get("call_id")
            if not isinstance(call_id, str) or not SAFE_CALL.fullmatch(call_id):
                raise HTTPException(502, "Invalid model tool result")
            messages.append({"role": "tool", "tool_call_id": call_id,
                             "content": str(item.get("output", ""))[:16_000]})
        elif kind == "message":
            flush()
            content = item.get("content", [])
            if not isinstance(content, list):
                raise HTTPException(502, "Invalid assistant message")
            text = "\n".join(str(c.get("text", "")) for c in content
                             if isinstance(c, dict) and c.get("type") == "output_text")
            if text:
                messages.append({"role": "assistant", "content": text[:16_000]})
        elif item.get("role") in ("user", "assistant", "system"):
            flush()
            text = item.get("content", "")
            if not isinstance(text, str):
                raise HTTPException(502, "Non-text item in SONIC brain chat")
            # Never promote untrusted chat history to system authority.
            messages.append({"role": "user" if item["role"] == "system" else item["role"],
                             "content": text[:20_000]})
        elif kind == "reasoning":
            # OpenAI's private internal reasoning items cannot be converted
            # to third-party model context. Never transmit them.
            continue
        else:
            raise HTTPException(502, "Unknown model conversation item")
    flush()
    return messages


def _chat_tools(tools: list[dict]) -> list[dict]:
    adapted = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function" or \
                not isinstance(tool.get("name"), str) or not SAFE_TOOL.fullmatch(tool["name"]):
            raise HTTPException(502, "Invalid SONIC tool definition")
        adapted.append({"type": "function", "function": {
            "name": tool["name"], "description": tool.get("description", "")[:1000],
            "parameters": tool.get("parameters", {}),
        }})
    return adapted


async def complete(client: httpx.AsyncClient, request: dict, selection: Selection) -> dict:
    """Single provider HTTP call, no cross-provider retries/fallback."""
    key = setting("OPENAI_API_KEY" if selection.provider == "openai" else "OPENROUTER_API_KEY")
    if not key:
        raise HTTPException(503, "Selected SONIC model API key is not configured")
    if selection.provider == "openai":
        url = OPENAI_URL
        payload = {**request, "model": selection.model}
    elif selection.provider == "openrouter":
        url = OPENROUTER_URL
        payload = {"model": selection.model,
                   "messages": _chat_messages(request["input"], request["instructions"]),
                   "tools": _chat_tools(request.get("tools", [])),
                   "tool_choice": request.get("tool_choice", "auto"),
                   "parallel_tool_calls": False, "stream": False,
                   "max_tokens": max(100, min(2400, int(request.get("max_output_tokens", 1800)))),
                   "reasoning": {"effort": "low"},
                   "usage": {"include": True}}
        if not payload["tools"]:
            payload.pop("tools")
            payload.pop("tool_choice")
    else:
        raise HTTPException(503, "Unsupported SONIC brain provider")

    try:
        response = await client.post(url, headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json",
            **({"X-Title": "SONIC Intelligence Console"} if selection.provider == "openrouter" else {}),
        }, json=payload)
    except httpx.RequestError:
        raise HTTPException(502, "SONIC brain provider connection failed") from None

    if response.status_code != 200:
        # Never reflect upstream body: it could include prompts, key metadata or
        # untrusted request details. No automatic paid retry.
        raise HTTPException(502, "SONIC brain provider rejected request (HTTP %d)" % response.status_code)

    try:
        data = response.json()
        if selection.provider == "openai":
            if not isinstance(data, dict) or not isinstance(data.get("output"), list):
                raise ValueError("Malformed Responses result")
            return data
        choice = data["choices"][0]
        finish = choice.get("finish_reason")
        message = choice["message"]
        if not isinstance(message, dict) or finish not in ("stop", "tool_calls"):
            raise ValueError("Incomplete provider response")
        tool_calls = message.get("tool_calls") or []
        if not isinstance(tool_calls, list) or len(tool_calls) > 10:
            raise ValueError("Invalid tool calls")
        out = []
        for call in tool_calls:
            if not isinstance(call, dict) or call.get("type") != "function":
                raise ValueError("Unknown tool call type")
            fn = call["function"]
            call_id, name, arguments = call["id"], fn["name"], fn.get("arguments", "{}")
            if not isinstance(call_id, str) or not SAFE_CALL.fullmatch(call_id) \
                    or not isinstance(name, str) or not SAFE_TOOL.fullmatch(name) \
                    or not isinstance(arguments, str) or len(arguments) > 10_000:
                raise ValueError("Malformed tool call")
            try:
                parsed_arguments = json.loads(arguments)
            except ValueError:
                raise ValueError("Invalid JSON tool arguments") from None
            if not isinstance(parsed_arguments, dict):
                raise ValueError("Tool arguments must be an object")
            out.append({"type": "function_call", "call_id": call_id,
                        "name": name, "arguments": arguments})
        if out and finish != "tool_calls":
            raise ValueError("Tool-call finish reason mismatch")
        if not out:
            if finish != "stop":
                raise ValueError("Missing tool calls")
            content = message.get("content")
            if isinstance(content, list):
                content = "\n".join(str(x.get("text", "")) for x in content
                                    if isinstance(x, dict) and x.get("type") == "text")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Empty text result")
            out = [{"type": "message", "content": [{"type": "output_text", "text": content[:12_000]}]}]
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        normalized = normalized_usage(usage)
        return {"status": "completed", "output": out,
                "usage": {"input_tokens": normalized["input_tokens"],
                          "output_tokens": normalized["output_tokens"],
                          "cost": normalized["cost_usd"]}}
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        raise HTTPException(502, "SONIC brain provider response could not be verified") from None
