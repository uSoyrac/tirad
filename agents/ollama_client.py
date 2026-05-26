"""
agents/ollama_client.py — Yerel Ollama LLM İstemcisi
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Desteklenen modeller (ücretsiz, yerel):
  • llama3:8b / llama3:70b     → Genel amaçlı
  • deepseek-r1:7b / :14b      → Derin akıl yürütme (en iyi tartışma için)
  • qwen2.5:7b / qwen2.5:14b   → Finans anlayışı güçlü
  • mistral:7b                 → Hızlı, verimli

Kurulum:
  brew install ollama   (veya https://ollama.ai)
  ollama serve
  ollama pull deepseek-r1:7b
  ollama pull qwen2.5:7b

Fallback: Ollama mevcut değilse kural tabanlı analiz kullanılır.
"""

import json
import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger("agents.ollama")

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL     = os.getenv("OLLAMA_MODEL",      "deepseek-r1:7b")
QUICK_MODEL       = os.getenv("OLLAMA_QUICK_MODEL", "qwen2.5:7b")
TIMEOUT           = int(os.getenv("OLLAMA_TIMEOUT", "45"))


# ══════════════════════════════════════════════════════════════════════
#  BAĞLANTI KONTROLÜ
# ══════════════════════════════════════════════════════════════════════

def is_available() -> bool:
    """Ollama sunucusunun çalışıp çalışmadığını kontrol eder."""
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def list_models() -> list:
    """Mevcut Ollama modellerini listeler."""
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


def best_available_model(prefer_reasoning: bool = True) -> Optional[str]:
    """
    Mevcut modeller içinden en iyi seçeneği döner.
    Öncelik: deepseek-r1 → qwen2.5 → llama3 → mistral → herhangi biri
    """
    models = list_models()
    if not models:
        return None

    priority = (
        ["deepseek-r1:14b", "deepseek-r1:8b", "deepseek-r1:7b"]
        if prefer_reasoning else []
    ) + [
        "qwen2.5:14b", "qwen2.5:7b", "qwen2.5:3b",
        "llama3:70b", "llama3:8b", "llama3.2:3b",
        "mistral:7b", "phi3:mini",
    ]

    for pref in priority:
        for m in models:
            if pref in m or m.startswith(pref.split(":")[0]):
                return m

    return models[0] if models else None


# ══════════════════════════════════════════════════════════════════════
#  TEMEL SORGU
# ══════════════════════════════════════════════════════════════════════

def query(
    prompt:     str,
    system:     str = "",
    model:      Optional[str] = None,
    temperature: float = 0.3,
    max_tokens:  int   = 800,
    stream:      bool  = False,
) -> Optional[str]:
    """
    Ollama'ya sorgu gönderir.
    Döner: str (yanıt) veya None (başarısız).
    """
    if model is None:
        model = best_available_model() or DEFAULT_MODEL

    payload = {
        "model":   model,
        "prompt":  prompt,
        "system":  system,
        "stream":  stream,
        "options": {
            "temperature":   temperature,
            "num_predict":   max_tokens,
            "top_p":         0.9,
        },
    }

    try:
        t0 = time.time()
        r  = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json=payload,
            timeout=TIMEOUT,
        )
        elapsed = time.time() - t0

        if r.status_code == 200:
            response = r.json().get("response", "").strip()
            logger.debug(f"Ollama ({model}) yanıt: {elapsed:.1f}s  {len(response)} karakter")
            return response
        else:
            logger.warning(f"Ollama HTTP {r.status_code}: {r.text[:200]}")
            return None

    except requests.exceptions.Timeout:
        logger.warning(f"Ollama timeout ({TIMEOUT}s) — model: {model}")
        return None
    except Exception as e:
        logger.debug(f"Ollama hatası: {e}")
        return None


def query_json(
    prompt: str,
    system: str = "",
    model:  Optional[str] = None,
    default: dict = None,
) -> dict:
    """
    JSON çıktı bekleyen sorgu. Parse başarısızsa default döner.
    """
    if default is None:
        default = {}

    sys_json = (system or "") + "\n\nMutlaka geçerli JSON döndür. Açıklama ekleme, sadece JSON."
    response = query(prompt, sys_json, model, temperature=0.1, max_tokens=600)

    if not response:
        return default

    # JSON bloğunu bul
    try:
        # ```json ... ``` veya { ... } formatını dene
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception:
        pass

    return default
