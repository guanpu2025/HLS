"""LLM backend.

Two backends, one code path:

    LLM_BACKEND=mock      no network, no key. Returns a canned stub derived from
                          the interface. Use this to verify the run.sh contract
                          and the judging pipeline without a GPU or an API key.

    LLM_BACKEND=openai    any OpenAI-compatible /chat/completions endpoint.
                          This covers BOTH a commercial API bought by the team
                          (development only) AND a local vLLM server (what the
                          submission must actually use).

    development   LLM_BASE_URL=https://api.deepseek.com/v1
    local model   LLM_BASE_URL=http://localhost:8000/v1

Only the environment variables change; the agent does not.

NOTE FOR SUBMISSION: the final run happens in an offline sandbox. MODEL.md must
declare locally deployable open weights. A commercial API fails conditions 2.1
and 2.3 of the scoring rules and produces no run-based score at all.
"""

from __future__ import annotations

import json
import os
import re
import textwrap


class LLMError(RuntimeError):
    pass


class LLMResult:
    def __init__(self, text: str, tokens_in: int = 0, tokens_out: int = 0):
        self.text = text
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out


class LLM:
    def __init__(self) -> None:
        self.backend = os.environ.get("LLM_BACKEND", "openai").strip().lower()
        self.model = os.environ.get("LLM_MODEL", "Coder390-Q6_K")
        self.base_url = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")
        self.api_key = os.environ.get("LLM_API_KEY", "dummy")
        self.max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "8192"))
        self.temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
        self.timeout_s = float(os.environ.get("LLM_TIMEOUT_S", "900"))

        if self.backend == "openai" and not self.base_url:
            raise LLMError("LLM_BACKEND=openai requires LLM_BASE_URL")

    def describe(self) -> dict:
        return {
            "backend": self.backend,
            "model": self.model,
            "base_url": self.base_url or None,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

    def chat(self, messages: list[dict], temperature: float | None = None,
             max_tokens: int | None = None) -> LLMResult:
        if self.backend == "mock":
            return self._chat_mock(messages)
        if self.backend == "openai":
            return self._chat_openai(messages, temperature, max_tokens)
        raise LLMError(f"unknown LLM_BACKEND: {self.backend!r}")

    # ---------------------------------------------------------------- openai

    def _chat_openai(self, messages: list[dict], temperature: float | None = None,
                     max_tokens: int | None = None) -> LLMResult:
        import requests  # imported lazily so mock mode needs no dependency

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens if max_tokens is None else int(max_tokens),
            "temperature": self.temperature if temperature is None else temperature,
            "stream": False,
        }

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            data=json.dumps(payload),
            timeout=self.timeout_s,
        )
        if resp.status_code != 200:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:500]}")

        body = resp.json()
        try:
            text = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected response shape: {str(body)[:500]}") from exc

        usage = body.get("usage") or {}
        return LLMResult(
            text=text,
            tokens_in=int(usage.get("prompt_tokens", 0) or 0),
            tokens_out=int(usage.get("completion_tokens", 0) or 0),
        )

    # ------------------------------------------------------------------ mock

    def _chat_mock(self, messages: list[dict]) -> LLMResult:
        """Return something shaped like a real answer, without a model.

        The point is to exercise the plumbing -- prompt assembly, code
        extraction, tool invocation, trace writing, the HTTP shell -- not to
        produce a correct kernel. The stub compiles about as often as it does
        not, which is realistic enough for a smoke test.
        """
        user = "\n".join(m["content"] for m in messages if m["role"] == "user")
        signature = _first_signature(user)
        header = _guessed_header(user)

        if signature:
            body = textwrap.dedent(
                f"""\
                #include "{header}"

                {signature.rstrip(';')} {{
                #pragma HLS INLINE off
                    // MOCK BACKEND -- placeholder body, not a real solution.
                    // Set LLM_BACKEND=openai to get a generated implementation.
                }}
                """
            )
        else:
            body = "// MOCK BACKEND: could not read a signature from interface.txt\n"

        text = "以下是实现：\n\n```cpp\n" + body + "```\n"
        return LLMResult(text=text, tokens_in=len(user) // 4, tokens_out=len(text) // 4)


# --------------------------------------------------------------------- utils

_SIG_RE = re.compile(
    r"^\s*(?:static\s+|inline\s+|extern\s+\"C\"\s+)*"
    r"(?:void|int|unsigned|float|double|[A-Za-z_][\w:]*)\s+"
    r"[A-Za-z_]\w*\s*\([^;{]*\)\s*;",
    re.MULTILINE | re.DOTALL,
)


def _first_signature(text: str) -> str | None:
    m = _SIG_RE.search(text)
    return m.group(0).strip() if m else None


def _guessed_header(text: str) -> str:
    m = re.search(r'#include\s+"([^"]+\.h(?:pp)?)"', text)
    if m:
        return m.group(1)
    m = re.search(r"#ifndef\s+([A-Z0-9_]+)_H", text)
    if m:
        return m.group(1).lower() + ".h"
    return "kernel.h"


_FENCE_LABEL = r"cpp|c\+\+|c|hls|"
_FENCE_OPEN_RE = re.compile(rf"```(?:{_FENCE_LABEL})\s*\n", re.IGNORECASE)
_FENCE_PAIRED_RE = re.compile(
    rf"```(?:{_FENCE_LABEL})\s*\n(.*?)```", re.DOTALL | re.IGNORECASE,
)


def _is_fence_line(line: str) -> bool:
    return line.lstrip().startswith("```")


def _strip_fence_lines(text: str) -> str:
    """Drop markdown fence marker lines. Never return a ```-prefixed line."""
    lines = text.splitlines()
    while lines and _is_fence_line(lines[0]):
        lines.pop(0)
    while lines and _is_fence_line(lines[-1]):
        lines.pop()
    lines = [ln for ln in lines if not _is_fence_line(ln)]
    body = "\n".join(lines).strip()
    return (body + "\n") if body else ""


def has_unclosed_fence(text: str) -> bool:
    """True when an opening ```cpp / ```c++ / ```hls / ``` fence has no closer."""
    rest = _FENCE_PAIRED_RE.sub("", text)
    opened = _FENCE_OPEN_RE.search(rest)
    return bool(opened and rest[opened.end():].strip())


def extract_code(text: str) -> str:
    """Pull the C++ out of a model reply.

    Models wrap code in fences with wildly inconsistent labels, and small models
    sometimes emit prose after the closing fence, or no fence at all. Handle the
    three cases in decreasing order of confidence.
    """
    blocks = _FENCE_PAIRED_RE.findall(text)
    if blocks:
        # 取最长的代码块：模型常先回显接口。
        return _strip_fence_lines(max(blocks, key=len))

    opened = _FENCE_OPEN_RE.search(text)
    if opened and text[opened.end():].strip():
        return _strip_fence_lines(text[opened.end():])

    # 无代码围栏时，若整体形似代码则全部取用。剥掉首尾围栏行。
    if "#include" in text or "void " in text or "#pragma" in text:
        return _strip_fence_lines(text)

    return ""
