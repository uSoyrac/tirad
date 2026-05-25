"""
APScheduler — tüm analiz akışını yönetir.
"""
import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from main_engine import run_full_scan

logger = logging.getLogger(__name__)


def start_scheduler(config: dict):
    sched_cfg = config.get("scheduler", {})
    output_cfg = config.get("output", {})

    scheduler = BlockingScheduler(timezone="UTC")

    # Kripto tarama — her 4 saatte bir (4H mum kapanışı)
    crypto_interval = sched_cfg.get("crypto_scan_interval_minutes", 240)
    scheduler.add_job(
        lambda: run_full_scan(config, asset_types=["crypto"]),
        IntervalTrigger(minutes=crypto_interval),
        id="crypto_scan",
        name="Kripto Tarama",
        next_run_time=datetime.utcnow(),  # İlk çalışma hemen
    )

    # BIST tarama — her 1 saatte bir (Borsa İstanbul seansları)
    if config.get("bist_watchlist", {}).get("enabled", False):
        bist_interval = sched_cfg.get("bist_scan_interval_minutes", 60)
        scheduler.add_job(
            lambda: run_full_scan(config, asset_types=["bist"]),
            IntervalTrigger(minutes=bist_interval),
            id="bist_scan",
            name="BIST Tarama",
        )

    # Sosyal veri güncelleme — her 6 saatte bir
    social_interval = sched_cfg.get("social_update_interval_minutes", 360)
    scheduler.add_job(
        lambda: run_full_scan(config, social_only=True),
        IntervalTrigger(minutes=social_interval),
        id="social_update",
        name="Sosyal Güncelleme",
    )

    # Günlük rapor
    if output_cfg.get("email", {}).get("send_daily_report", True):
        report_hour = output_cfg.get("email", {}).get("daily_report_hour", 8)
        scheduler.add_job(
            lambda: run_full_scan(config, report_only=True),
            CronTrigger(hour=report_hour, minute=0),
            id="daily_report",
            name="Günlük Rapor",
        )

    logger.info("Zamanlayıcı başlatıldı — Ctrl+C ile durdurulabilir")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Zamanlayıcı durduruldu")
        scheduler.shutdown()
