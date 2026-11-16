"""Minimal Groq chat-completions client (OpenAI-compatible HTTP API)."""

import os
import re
import time

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_RATE_LIMIT_RETRIES = 2
MAX_WAIT_S = 15.0


def _retry_after_seconds(body: str) -> float:
    """Groq says 'Please try again in 5.8s' on 429s. Honor it, capped."""
    m = re.search(r"try again in ([\d.]+)s", body)
    wait = float(m.group(1)) if m else 2.0
    return min(wait + 0.25, MAX_WAIT_S)


class GroqLLM:
    def __init__(self, model=None, api_key=None, timeout_s=60):
        self.model = model or os.environ.get("TEXT2SQL_MODEL", DEFAULT_MODEL)
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.timeout_s = timeout_s

    def chat(self, messages, temperature=0.0, max_tokens=1024):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = None
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=self.timeout_s)
            if resp.status_code != 429 or attempt == MAX_RATE_LIMIT_RETRIES:
                break
            time.sleep(_retry_after_seconds(resp.text))
        if resp.status_code >= 400:
            raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"] or ""
