"""minimal openai-compatible chat client, stdlib urllib only.

the rag consumer's only llm dependency. reads LLM_BASE_URL, LLM_MODEL,
LLM_API_KEY from env. no http library on purpose: the core stays dependency-free
and the rag extra needs only the neo4j driver plus a reachable openai-compatible
llm (ollama, llama.cpp, vLLM, openai, ...).
"""
import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE = "http://localhost:11434/v1"   # ollama's openai-compatible endpoint
DEFAULT_MODEL = "llama3.1"
TIMEOUT = 60


def chat(messages, temperature=0, model=None):
    """POST messages to {LLM_BASE_URL}/chat/completions, return the reply text."""
    base = os.environ.get("LLM_BASE_URL", DEFAULT_BASE).rstrip("/")
    model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    body = json.dumps({"model": model, "messages": messages,
                       "temperature": temperature}).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    key = os.environ.get("LLM_API_KEY")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError) as e:
        raise SystemExit(
            f"LLM unreachable at {base} (set LLM_BASE_URL/LLM_MODEL/LLM_API_KEY): {e}"
        ) from e
    return data["choices"][0]["message"]["content"]
