"""LLM access with graceful degradation.

Backends, tried in this order when SCOUT_LLM_BACKEND=auto:
  1. anthropic   - official SDK, needs ANTHROPIC_API_KEY
  2. claude-cli  - `claude -p` (Claude Code CLI on the operator's machine)
  3. ollama      - local model on http://127.0.0.1:11434
  4. none        - deterministic fallback (the pipeline still completes)

Every call asks for strict JSON and validates it; on any failure the caller
gets `None` and must fall back to its heuristic path. The demo never depends
on an LLM being reachable.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from typing import Any

import httpx

from .config import settings

log = logging.getLogger("scout.llm")


def _extract_json(text: str) -> Any | None:
    if not text:
        return None
    text = text.strip()
    # strip ```json fences
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    # first {...} or [...] block
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = text.find(opener), text.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(text[i : j + 1])
            except ValueError:
                continue
    return None


class LLM:
    def __init__(self, backend: str | None = None):
        self.backend = (backend or settings.SCOUT_LLM_BACKEND or "auto").lower()
        self.resolved: str | None = None
        self.last_error: str | None = None
        self._dead: set[str] = set()  # backends that failed once in this process: never retried

    # ----------------------------------------------------------- resolution
    def _candidates(self) -> list[str]:
        if self.backend != "auto":
            return [self.backend]
        order: list[str] = []
        if settings.ANTHROPIC_API_KEY:
            order.append("anthropic")
        if shutil.which("claude"):
            order.append("claude-cli")
        order.append("ollama")
        order.append("none")
        return order

    def describe(self) -> str:
        return self.resolved or self.backend

    # ------------------------------------------------------------- generate
    def json(self, system: str, user: str, *, max_tokens: int = 1500) -> Any | None:
        """Return parsed JSON or None. Never raises."""
        for backend in self._candidates():
            if backend == "none":
                self.resolved = "none"
                return None
            if backend in self._dead:
                continue
            try:
                text = getattr(self, f"_call_{backend.replace('-', '_')}")(system, user, max_tokens)
            except Exception as exc:  # noqa: BLE001 - degrade, never crash the run
                self.last_error = f"{backend}: {exc}"
                log.warning("LLM backend %s failed: %s", backend, exc)
                self._dead.add(backend)
                if self.backend != "auto":
                    return None
                continue
            parsed = _extract_json(text or "")
            if parsed is not None:
                self.resolved = backend
                return parsed
            self.last_error = f"{backend}: non-JSON output"
            if self.backend != "auto":
                return None
        return None

    # -------------------------------------------------------------- backends
    def _call_anthropic(self, system: str, user: str, max_tokens: int) -> str:
        import anthropic  # lazy: optional dependency

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=settings.SCOUT_LLM_TIMEOUT_S)
        msg = client.messages.create(
            model=settings.SCOUT_ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(getattr(block, "text", "") for block in msg.content)

    def _call_claude_cli(self, system: str, user: str, max_tokens: int) -> str:
        prompt = f"{system}\n\n---\n\n{user}\n\nRespond with JSON only."
        proc = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--model", settings.SCOUT_CLAUDE_CLI_MODEL, prompt],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,  # no stdin: skips the CLI's 3 s wait for piped input
            timeout=settings.SCOUT_LLM_TIMEOUT_S,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude -p exited {proc.returncode}: {proc.stderr[:300]}")
        try:
            envelope = json.loads(proc.stdout)
            # Claude Code's json envelope carries the assistant text in `result`
            if isinstance(envelope, dict) and "result" in envelope:
                return str(envelope["result"])
        except ValueError:
            pass
        return proc.stdout

    def _call_ollama(self, system: str, user: str, max_tokens: int) -> str:
        r = httpx.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": settings.SCOUT_OLLAMA_MODEL,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.2, "num_predict": max_tokens},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
            timeout=settings.SCOUT_LLM_TIMEOUT_S,
        )
        r.raise_for_status()
        return (r.json().get("message") or {}).get("content", "")
