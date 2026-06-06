"""
Ana analiz motoru — tüm katmanları orkestrasyonla birleştirir.
Bir tarama döngüsü: Veri → Analiz → Skor → Setup → Output
"""
import logging
import os
from datetime import datetime
from typing import Optional

import yaml

from market.data_fetcher import MarketDataFetcher
from market.multi_tf_builder import build_multi_tf
from analysis.smc_engine import analyze_smc
from analysis.classic_indicators import analyze_classic
from analysis.institutional import analyze_institutional
from analysis.composite_scorer import compute_composite, CompositeScore
from signals.trade_setup import calculate_trade_setup
from signals.position_sizer import calculate_position
from signals.claude_synthesizer import synthesize_with_claude
from data.collectors.web_scraper import collect_all_news
from data.collectors.youtube_collector import collect_youtube_data, extract_text_from_youtube_data
from nlp.entity_extractor import extract_crypto_mentions, get_top_mentioned_assets
from nlp.sentiment_analyzer import batch_sentiment
from data.database.db import save_signal, save_social_mention, get_recent_signals
from output.email_notifier import send_signal_email, send_daily_report
from output.console_printer import print_signal

logger = logging.getLogger(__name__)

_social_cache: dict = {}  # {symbol: social_data} — 6 saatte bir güncellenir
_social_last_update: Optional[datetime] = None


def load_config(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def update_social_intelligence(config: dict) -> dict:
    """Web + YouTube'dan sosyal veri toplar, asset başına sentiment döndürür."""
    global _social_cache, _social_last_update

    logger.info("Sosyal istihbarat güncelleniyor...")
    all_texts = []
    symbol_texts: dict[str, list[str]] = {}

    # Web haberler
    news = collect_all_news(config)
    for article in news:
        text = article.get("title", "")
        all_texts.append(text)

        # CryptoPanic'te hangi coin var
        if "currencies" in article:
            for currency in article["currencies"]:
                sym = f"{currency}/USDT"
                symbol_texts.setdefault(sym, []).append(text)
        else:
            # Entity extraction
            from nlp.entity_extractor import extract_crypto_mentions
            mentions = extract_crypto_mentions(text)
            for sym, count in mentions.items():
                symbol_texts.setdefault(f"{sym}/USDT", []).append(text * count)

    # YouTube
    yt_cfg = config.get("social", {}).get("youtube", {})
    if yt_cfg.get("enabled", False):
        channels = []
        for lang, ch_list in yt_cfg.get("channels", {}).items():
            if isinstance(ch_list, list):
                channels.extend(ch_list)

        if channels:
            yt_data = collect_youtube_data(
                channels,
                max_videos=yt_cfg.get("max_videos_per_channel", 3),
                max_chars=yt_cfg.get("max_transcript_chars", 8000),
            )
            yt_texts = extract_text_from_youtube_data(yt_data)
            all_texts.extend(yt_texts)

            for item in yt_data:
                text = " ".join([item.get("title", ""), item.get("transcript", "")])
                from nlp.entity_extractor import extract_crypto_mentions
                mentions = extract_crypto_mentions(text)
                for sym, count in mentions.items():
                    symbol_texts.setdefault(f"{sym}/USDT", []).append(text)

    # Sentiment hesaplama — her sembol için
    social_scores = {}
    for sym, texts in symbol_texts.items():
        if not texts:
            continue
        sentiment = batch_sentiment(texts)
        social_scores[sym] = {
            "sentiment": sentiment["avg_score"],
            "platform_count": sentiment["platform_count"],
            "bullish_ratio": sentiment["bullish_ratio"],
            "mention_count": len(texts),
            "label": sentiment["label"],
        }
        # DB'ye kaydet
        save_social_mention({
            "symbol": sym, "source": "multi",
            "language": "mixed",
            "sentiment": sentiment["avg_score"],
            "mention_count": len(texts),
            "raw_text": "",
        })

    _social_cache = social_scores
    _social_last_update = datetime.utcnow()
    logger.info(f"Sosyal güncelleme tamamlandı: {len(social_scores)} asset")
    return social_scores


def get_watchlist(config: dict, social_scores: dict, asset_type: str = "crypto") -> list[str]:
    """Sabit liste + sosyal keşif ile tarama listesi oluşturur."""
    if asset_type == "bist":
        bist_cfg = config.get("bist_watchlist", {})
        return bist_cfg.get("symbols", []) if bist_cfg.get("enabled", True) else []

    # Kripto
    fixed = list(config.get("crypto_watchlist", ["BTC/USDT", "ETH/USDT", "SOL/USDT"]))

    social_cfg = config.get("social_discovery", {})
    if social_cfg.get("enabled", True) and social_scores:
        top_n = social_cfg.get("top_n", 5)
        min_mentions = social_cfg.get("min_mention_count", 3)

        # Sosyal puanlara göre sırala
        discovered = sorted(
            [(sym, d) for sym, d in social_scores.items() if d.get("mention_count", 0) >= min_mentions],
            key=lambda x: x[1].get("mention_count", 0),
            reverse=True,
        )[:top_n]

        for sym, _ in discovered:
            if sym not in fixed:
                fixed.append(sym)
                logger.info(f"Sosyal keşif: {sym} watchlist'e eklendi")

    return fixed


def analyze_symbol(
    symbol: str,
    asset_type: str,
    fetcher: MarketDataFetcher,
    config: dict,
    social_scores: dict,
) -> Optional[CompositeScore]:
    """Tek bir sembol için tam analiz yapar."""
    logger.info(f"Analiz başlıyor: {symbol} ({asset_type})")

    # Multi-TF veri
    mtf = build_multi_tf(symbol, fetcher)
    if not mtf.is_complete():
        logger.warning(f"{symbol}: Eksik veri, atlanıyor")
        return None

    primary_df = mtf.h4  # Ana sinyal TF
    is_bist = asset_type == "bist"

    # SMC analizi (4H)
    smc_cfg = config.get("smc", {})
    smc = analyze_smc(primary_df, smc_cfg)

    # Klasik indikatörler (4H)
    classic_cfg = config.get("technical", {})
    classic = analyze_classic(primary_df, classic_cfg)

    # Kurumsal metrikler
    extras = mtf.extras if not is_bist else {}
    institutional = analyze_institutional(primary_df, extras, is_bist=is_bist)

    # Multi-TF trend
    tf_trends = {}
    for tf_key, tf_df in [("1w", mtf.weekly), ("1d", mtf.daily), ("4h", mtf.h4), ("1h", mtf.h1)]:
        if not tf_df.empty:
            tf_smc = analyze_smc(tf_df, smc_cfg)
            tf_trends[tf_key] = tf_smc.trend

    # Sosyal puan
    social_data = social_scores.get(symbol)

    # Composite skor
    score = compute_composite(
        symbol=symbol,
        asset_type=asset_type,
        smc=smc,
        classic=classic,
        institutional=institutional,
        tf_trends=tf_trends,
        social_data=social_data,
    )

    return score


def run_full_scan(
    config: dict,
    asset_types: list = None,
    social_only: bool = False,
    report_only: bool = False,
):
    """Tam tarama döngüsü — tüm asset'ler analiz edilir."""
    if asset_types is None:
        asset_types = ["crypto", "bist"]

    logger.info(f"{'='*50}")
    logger.info(f"Tarama başlıyor: {datetime.utcnow().isoformat()}")

    # Günlük rapor
    if report_only:
        recent = get_recent_signals(50)
        send_daily_report(recent, config)
        return

    # Sosyal güncelleme
    global _social_cache, _social_last_update
    needs_social_update = (
        not _social_cache or
        _social_last_update is None or
        (datetime.utcnow() - _social_last_update).seconds > 3600 * 6
    )

    if social_only or needs_social_update:
        _social_cache = update_social_intelligence(config)
        if social_only:
            return

    fetcher = MarketDataFetcher()
    output_cfg = config.get("output", {})
    pos_cfg = config.get("position_sizing", {})
    balance = float(os.getenv("ACCOUNT_BALANCE", pos_cfg.get("account_balance", 10000)))
    email_cfg = output_cfg.get("email", {})

    session_signals = []

    for asset_type in asset_types:
        watchlist = get_watchlist(config, _social_cache, asset_type)
        logger.info(f"{asset_type.upper()} watchlist ({len(watchlist)}): {watchlist}")

        for symbol in watchlist:
            try:
                score = analyze_symbol(symbol, asset_type, fetcher, config, _social_cache)
                if score is None:
                    continue

                # Sadece sinyal varsa devam et
                if score.signal_level == "NO_SIGNAL":
                    logger.debug(f"{symbol}: Sinyal yok ({score.composite:.1f}/10)")
                    continue

                # Trade setup
                smc_for_setup = analyze_smc(
                    fetcher.fetch(symbol, "4h", 300),
                    config.get("smc", {})
                )
                current_price = score.current_price or 0
                setup = calculate_trade_setup(
                    score, smc_for_setup, current_price,
                    config.get("position_sizing", {})
                )

                # Pozisyon büyüklüğü
                pos = None
                if setup and setup.valid:
                    pos = calculate_position(
                        setup, score, balance,
                        risk_pct=pos_cfg.get("risk_per_trade", 0.02),
                        max_leverage=pos_cfg.get("max_leverage", 5),
                    )

                # Claude sentezi
                claude_text = synthesize_with_claude(score, setup, pos, config.get("claude", {}))

                # Konsol çıktı
                if output_cfg.get("console", {}).get("enabled", True):
                    print_signal(score, setup, pos, claude_text)

                # DB'ye kaydet
                signal_data = {
                    "symbol": score.symbol,
                    "asset_type": score.asset_type,
                    "direction": score.direction,
                    "composite_score": score.composite,
                    "smc_score": score.smc_score,
                    "classic_score": score.classic_score,
                    "institutional_score": score.institutional_score,
                    "mtf_score": score.mtf_score,
                    "social_score": score.social_score,
                    "signal_level": score.signal_level,
                    "entry_low": setup.entry_low if setup else None,
                    "entry_high": setup.entry_high if setup else None,
                    "stop_loss": setup.stop_loss if setup else None,
                    "tp1": setup.tp1 if setup else None,
                    "tp2": setup.tp2 if setup else None,
                    "tp3": setup.tp3 if setup else None,
                    "leverage": pos.leverage if pos else None,
                }
                save_signal(signal_data)
                session_signals.append(signal_data)

                # Email gönder
                should_email = (
                    (score.signal_level == "STRONG" and email_cfg.get("send_on_strong", True)) or
                    (score.signal_level == "MEDIUM" and email_cfg.get("send_on_medium", True))
                )
                if email_cfg.get("enabled", True) and should_email:
                    send_signal_email(score, setup, pos, claude_text, config)

            except Exception as e:
                logger.error(f"{symbol} analiz hatası: {e}", exc_info=True)

    logger.info(f"Tarama tamamlandı: {len(session_signals)} sinyal üretildi")
    return session_signals
