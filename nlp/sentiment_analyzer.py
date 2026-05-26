"""
Çok dilli sentiment analizi: TR / EN / DE
Ağır transformers modeli olmadan da çalışır (kelime bazlı fallback).
"""
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy import — sadece kullanıldığında yüklenir
_pipeline = None
_langdetect = None


def _get_langdetect():
    global _langdetect
    if _langdetect is None:
        try:
            from langdetect import detect
            _langdetect = detect
        except ImportError:
            logger.warning("langdetect yok, dil tespiti atlanıyor")
            _langdetect = lambda x: "en"
    return _langdetect


# ─── Kelime tabanlı fallback sentiment (model gerekmez) ─────
BULLISH_WORDS_EN = {
    "bull", "bullish", "moon", "pump", "breakout", "long", "buy", "accumulate",
    "support", "bounce", "recovery", "uptrend", "reversal", "oversold", "undervalued",
    "strong", "higher", "surge", "rally", "opportunity", "target", "hold",
}
BEARISH_WORDS_EN = {
    "bear", "bearish", "dump", "crash", "short", "sell", "resistance",
    "breakdown", "downtrend", "overbought", "overvalued", "weak", "lower",
    "correction", "drop", "fall", "risk", "warning",
}

BULLISH_WORDS_TR = {
    "boğa", "yükseliş", "alım", "destek", "toparlanma", "güçlü", "fırsat",
    "artış", "rally", "tükenme", "uzun", "al", "hedef", "pozitif", "umut",
    "dipten", "hacim artışı", "kırılım",
}
BEARISH_WORDS_TR = {
    "ayı", "düşüş", "satış", "direnç", "zayıf", "kırılım", "risk",
    "uyarı", "düzeltme", "çöküş", "sat", "negatif", "panik",
}

BULLISH_WORDS_DE = {
    "bullen", "bullish", "kaufen", "anstieg", "erholung", "stark", "chance",
    "aufwärtstrend", "unterstützung", "positiv",
}
BEARISH_WORDS_DE = {
    "bären", "bearish", "verkaufen", "absturz", "schwach", "risiko",
    "abwärtstrend", "widerstand", "negativ", "warnung",
}

LANG_WORDS = {
    "en": (BULLISH_WORDS_EN, BEARISH_WORDS_EN),
    "tr": (BULLISH_WORDS_TR, BEARISH_WORDS_TR),
    "de": (BULLISH_WORDS_DE, BEARISH_WORDS_DE),
}


@dataclass
class SentimentResult:
    score: float          # 0-1 (0.5 = nötr, >0.5 pozitif)
    label: str            # "BULLISH", "BEARISH", "NEUTRAL"
    confidence: float
    language: str
    method: str           # "transformers" veya "keyword"


def detect_language(text: str) -> str:
    try:
        detect = _get_langdetect()
        lang = detect(text[:500])
        return lang if lang in ["en", "tr", "de"] else "en"
    except Exception:
        return "en"


def keyword_sentiment(text: str, lang: str = "en") -> SentimentResult:
    """Hızlı kelime bazlı sentiment (transformer gerektirmez)."""
    text_lower = text.lower()
    bull_words, bear_words = LANG_WORDS.get(lang, LANG_WORDS["en"])

    bull_count = sum(1 for w in bull_words if w in text_lower)
    bear_count = sum(1 for w in bear_words if w in text_lower)

    total = bull_count + bear_count
    if total == 0:
        return SentimentResult(0.5, "NEUTRAL", 0.3, lang, "keyword")

    bull_ratio = bull_count / total
    score = 0.5 + (bull_ratio - 0.5) * 0.8  # Normalize to 0.1-0.9

    if score >= 0.6:
        label = "BULLISH"
    elif score <= 0.4:
        label = "BEARISH"
    else:
        label = "NEUTRAL"

    confidence = min(total / 10, 1.0) * 0.7  # Max 0.7 — keyword düşük güven

    return SentimentResult(score, label, confidence, lang, "keyword")


def try_transformers_sentiment(text: str, lang: str) -> Optional[SentimentResult]:
    """FinBERT veya BERTurk ile sentiment. Yüklenemezse None döner."""
    global _pipeline

    try:
        from transformers import pipeline as hf_pipeline

        if _pipeline is None:
            model_name = "ProsusAI/finbert" if lang in ["en", "de"] else "savasy/bert-base-turkish-sentiment-cased"
            logger.info(f"Transformers modeli yükleniyor: {model_name}")
            _pipeline = hf_pipeline(
                "sentiment-analysis", model=model_name,
                truncation=True, max_length=512,
            )

        result = _pipeline(text[:512])[0]
        label_raw = result["label"].lower()
        score_raw = result["score"]

        if "positive" in label_raw or "bullish" in label_raw or "pozitif" in label_raw:
            score = 0.5 + score_raw * 0.5
            label = "BULLISH"
        elif "negative" in label_raw or "bearish" in label_raw or "negatif" in label_raw:
            score = 0.5 - score_raw * 0.5
            label = "BEARISH"
        else:
            score = 0.5
            label = "NEUTRAL"

        return SentimentResult(score, label, score_raw, lang, "transformers")

    except Exception as e:
        logger.debug(f"Transformers sentiment başarısız: {e}")
        return None


def analyze_sentiment(text: str, use_transformers: bool = False) -> SentimentResult:
    """
    Tek metin için sentiment analizi.
    use_transformers=True → FinBERT/BERTurk (daha doğru ama yavaş)
    Fallback: kelime bazlı (hızlı, her zaman çalışır)
    """
    if not text or len(text.strip()) < 10:
        return SentimentResult(0.5, "NEUTRAL", 0.0, "en", "keyword")

    lang = detect_language(text)

    if use_transformers:
        result = try_transformers_sentiment(text, lang)
        if result:
            return result

    return keyword_sentiment(text, lang)


def batch_sentiment(texts: list[str], use_transformers: bool = False) -> dict:
    """
    Birden fazla metin için toplu sentiment.
    Döndürür: {
        'avg_score': float,
        'label': str,
        'bullish_count': int,
        'bearish_count': int,
        'neutral_count': int,
        'bullish_ratio': float,
        'platform_count': int (benzersiz dil sayısı),
    }
    """
    if not texts:
        return {"avg_score": 0.5, "label": "NEUTRAL", "bullish_count": 0,
                "bearish_count": 0, "neutral_count": 0, "bullish_ratio": 0.5,
                "platform_count": 0}

    results = [analyze_sentiment(t, use_transformers) for t in texts if t.strip()]

    if not results:
        return {"avg_score": 0.5, "label": "NEUTRAL", "bullish_count": 0,
                "bearish_count": 0, "neutral_count": 0, "bullish_ratio": 0.5,
                "platform_count": 0}

    avg_score = sum(r.score for r in results) / len(results)
    bull = sum(1 for r in results if r.label == "BULLISH")
    bear = sum(1 for r in results if r.label == "BEARISH")
    neutral = sum(1 for r in results if r.label == "NEUTRAL")

    if avg_score >= 0.58:
        label = "BULLISH"
    elif avg_score <= 0.42:
        label = "BEARISH"
    else:
        label = "NEUTRAL"

    unique_langs = len(set(r.language for r in results))

    return {
        "avg_score": round(avg_score, 3),
        "label": label,
        "bullish_count": bull,
        "bearish_count": bear,
        "neutral_count": neutral,
        "bullish_ratio": round(bull / len(results), 3),
        "platform_count": unique_langs,
        "sample_count": len(results),
    }
