#!/usr/bin/env python3
"""
setup_check.py — Sistem kurulum kontrolü
Canlı işleme geçmeden önce TÜM bileşenlerin çalıştığını doğrular.

Kullanım:
  python setup_check.py          # Tam kontrol
  python setup_check.py --quick  # Sadece kritik kontroller
  python setup_check.py --fix    # Eksikleri otomatik düzelt
"""
import warnings; warnings.filterwarnings("ignore")
import argparse, os, sys, time, importlib
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── Renkler (colorlog olmasa da çalışır) ─────────────────────
GR="\033[92m"; RD="\033[91m"; YL="\033[93m"; CY="\033[96m"
B="\033[1m"; DM="\033[2m"; R="\033[0m"
def ok(s):   return f"{GR}✅ {s}{R}"
def fail(s): return f"{RD}❌ {s}{R}"
def warn(s): return f"{YL}⚠️  {s}{R}"
def info(s): return f"{CY}ℹ️  {s}{R}"
def sep():   print("─" * 60)

RESULTS = []   # (name, status, detail)

def chk(name, status, detail=""):
    icon = ok("") if status else fail("")
    icon2 = "✅" if status else "❌"
    print(f"  {icon}{name:<34} {DM}{detail}{R}")
    RESULTS.append((name, status, detail))
    return status

def section(title):
    print(f"\n{'═'*60}")
    print(f"  {B}{CY}{title}{R}")
    print(f"{'═'*60}")


# ══════════════════════════════════════════════════════════════
#  1. PYTHON VERSİYONU
# ══════════════════════════════════════════════════════════════
def check_python():
    section("1. PYTHON VERSİYONU")
    v = sys.version_info
    ver_str = f"{v.major}.{v.minor}.{v.micro}"
    chk("Python versiyonu", v >= (3, 9), ver_str)
    chk("Python 3.12'den küçük (pandas uyumu)", v < (3, 13), ver_str)


# ══════════════════════════════════════════════════════════════
#  2. BAĞIMLILIKLAR
# ══════════════════════════════════════════════════════════════
REQUIRED_LIBS = [
    ("ccxt",             "ccxt",          "Binance API"),
    ("yfinance",         "yfinance",       "BIST verisi"),
    ("pandas",           "pandas",         "Veri işleme"),
    ("numpy",            "numpy",          "Matematik"),
    ("requests",         "requests",       "HTTP"),
    ("bs4",              "beautifulsoup4", "Web scraping"),
    ("dotenv",           "python-dotenv",  ".env okuma"),
    ("colorlog",         "colorlog",       "Renkli log"),
    ("apscheduler",      "APScheduler",    "Zamanlayıcı"),
    ("anthropic",        "anthropic",      "Claude API"),
]

OPTIONAL_LIBS = [
    ("transformers",     "transformers",   "FinBERT NLP (opsiyonel)"),
    ("torch",            "torch",          "PyTorch (opsiyonel)"),
    ("spacy",            "spacy",          "NLP (opsiyonel)"),
    ("playwright",       "playwright",     "Scraping (opsiyonel)"),
]

def check_libraries():
    section("2. KÜTÜPHANE KONTROLÜ")
    for mod, pkg, desc in REQUIRED_LIBS:
        try:
            importlib.import_module(mod)
            chk(f"{pkg}", True, desc)
        except ImportError:
            chk(f"{pkg}", False, f"Eksik — pip install {pkg}")

    print(f"\n  {DM}Opsiyonel:{R}")
    for mod, pkg, desc in OPTIONAL_LIBS:
        try:
            importlib.import_module(mod)
            print(f"  {ok('')}{pkg:<18} {DM}{desc}{R}")
        except ImportError:
            print(f"  {DM}  ○ {pkg:<18} {desc}{R}")


# ══════════════════════════════════════════════════════════════
#  3. .env KONTROLÜ
# ══════════════════════════════════════════════════════════════
def check_env():
    section("3. .env AYARLARI")

    env_file = Path(".env")
    chk(".env dosyası mevcut", env_file.exists(),
        ".env.example'ı kopyala" if not env_file.exists() else "✓")

    keys = {
        "BINANCE_API_KEY":    ("Kritik", "Binance API key"),
        "BINANCE_SECRET_KEY": ("Kritik", "Binance secret"),
        "EMAIL_SENDER":       ("Kritik", "Gmail gönderici"),
        "EMAIL_APP_PASSWORD": ("Kritik", "Gmail App Password"),
        "EMAIL_RECIPIENT":    ("Önerilen", "Bildirim adresi"),
        "ANTHROPIC_API_KEY":  ("Opsiyonel", "Claude sentezi"),
        "YOUTUBE_API_KEY":    ("Opsiyonel", "YouTube analizi"),
        "BOT_DRY_RUN":        ("Bot", "true/false"),
        "BOT_MIN_SCORE":      ("Bot", "Sinyal eşiği (önerilen: 6.0)"),
    }

    for key, (level, desc) in keys.items():
        val = os.getenv(key, "")
        has = bool(val and val not in ("your_anthropic_key_here",
                                       "your_binance_api_key_here",
                                       "your_binance_secret_here",
                                       "your_gmail@gmail.com",
                                       "your_16_char_app_password"))
        # Değeri maskele
        masked = (val[:4] + "***" + val[-2:]) if has and len(val) > 6 else ("(boş)" if not has else val)
        if level == "Kritik":
            chk(f"{key}", has, masked)
        elif level == "Bot":
            status = bool(val)
            print(f"  {'✅' if status else '⚠️ '} {key:<30} {DM}{val or '(boş — varsayılan kullanılır)'}{R}")
        else:
            print(f"  {DM}  ○ {key:<30} {masked} ({level}){R}")


# ══════════════════════════════════════════════════════════════
#  4. BİNANCE BAĞLANTI (READ-ONLY)
# ══════════════════════════════════════════════════════════════
def check_binance():
    section("4. BİNANCE BAĞLANTI TESTİ")
    try:
        import ccxt
        ex = ccxt.binance({
            "apiKey":  os.getenv("BINANCE_API_KEY", ""),
            "secret":  os.getenv("BINANCE_SECRET_KEY", ""),
            "enableRateLimit": True,
            "options": {"defaultType": "future"}
        })

        # Public endpoint — API key gerektirmez
        sys.stdout.write("  Binance sunucusu ... "); sys.stdout.flush()
        ticker = ex.fetch_ticker("BTC/USDT")
        btc_price = float(ticker["last"])
        chk("Binance bağlantısı", True, f"BTC/USDT=${btc_price:,.0f}")

        # ETH fiyat
        eth = float(ex.fetch_ticker("ETH/USDT")["last"])
        chk("ETH/USDT fiyat", eth > 100, f"${eth:,.2f}")

        # OHLCV
        bars = ex.fetch_ohlcv("BTC/USDT", "4h", limit=10)
        chk("4H OHLCV verisi", len(bars) == 10, f"{len(bars)} bar")

        # Funding rate (public)
        try:
            fr = ex.fetch_funding_rate("BTC/USDT")
            fr_val = fr.get("fundingRate", 0) * 100
            chk("Funding Rate", True, f"BTC FR={fr_val:.4f}%")
        except Exception:
            print(f"  {warn('Funding Rate alınamadı (opsiyonel)')}")

        # API key gerektiren endpoint (varsa)
        api_key = os.getenv("BINANCE_API_KEY", "")
        if api_key and api_key != "your_binance_api_key_here":
            try:
                bal = ex.fetch_balance({"type": "future"})
                usdt = float(bal.get("USDT", {}).get("free", 0))
                chk("Futures Bakiye (API)", True, f"${usdt:,.2f} USDT")
            except Exception as e:
                if "API-key" in str(e) or "signature" in str(e).lower():
                    chk("Futures Bakiye (API)", False, "API key/secret hatalı veya yetki yok")
                else:
                    chk("Futures Bakiye (API)", False, str(e)[:50])
        else:
            print(f"  {DM}  ○ Futures Bakiye — API key girilmedi (opsiyonel){R}")

    except Exception as e:
        chk("Binance bağlantısı", False, str(e)[:60])


# ══════════════════════════════════════════════════════════════
#  5. BIST VERİSİ (yfinance)
# ══════════════════════════════════════════════════════════════
def check_bist():
    section("5. BIST VERİSİ (yfinance)")
    try:
        import yfinance as yf
        sys.stdout.write("  THYAO.IS ... "); sys.stdout.flush()
        df = yf.Ticker("THYAO.IS").history(period="5d", interval="1d")
        ok_flag = not df.empty and len(df) > 0
        price = float(df["Close"].iloc[-1]) if ok_flag else 0
        chk("THYAO.IS (yfinance)", ok_flag, f"${price:.2f} TL" if ok_flag else "veri yok")
    except Exception as e:
        chk("BIST yfinance", False, str(e)[:50])


# ══════════════════════════════════════════════════════════════
#  6. SMC / CANLI TARAMA
# ══════════════════════════════════════════════════════════════
def check_live_scan():
    section("6. CANLI TARAMA (SMC Motoru)")
    try:
        sys.stdout.write("  live_scan.py import ... "); sys.stdout.flush()
        import live_scan as ls
        chk("live_scan.py import", True, "tüm fonksiyonlar yüklendi")

        # Kısa veri testi
        sys.stdout.write("  ETH/USDT SMC analizi ... "); sys.stdout.flush()
        df = ls.ohlcv("ETH/USDT", "4h", 200)
        chk("ETH/USDT veri", not df.empty, f"{len(df)} bar")

        if not df.empty:
            ms = ls.market_structure(df)
            chk("market_structure()", True, f"trend={ms['trend']}")

            bull_obs, bear_obs, _, _ = ls.order_blocks(df)
            chk("order_blocks()", True, f"bull={len(bull_obs)} bear={len(bear_obs)}")

            bull_fvg, bear_fvg = ls.fair_value_gaps(df)
            chk("fair_value_gaps()", True, f"bull={len(bull_fvg)} bear={len(bear_fvg)}")

            cl = ls.classic_indicators(df)
            rsi_val = cl.get("rsi", 0)
            chk("classic_indicators()", rsi_val > 0, f"RSI={rsi_val:.1f}")

    except Exception as e:
        chk("live_scan SMC motoru", False, str(e)[:60])


# ══════════════════════════════════════════════════════════════
#  7. BOT MODÜLLERİ
# ══════════════════════════════════════════════════════════════
def check_bot():
    section("7. BOT MODÜLLERİ")
    bot_modules = [
        ("bot.executor",         "Binance emir motoru"),
        ("bot.risk_manager",     "Pozisyon boyutlandırma"),
        ("bot.position_manager", "Pozisyon takibi"),
        ("bot.compound_tracker", "Bileşik büyüme"),
        ("bot.portfolio",        "Portfolio koordinatörü"),
    ]
    for mod, desc in bot_modules:
        try:
            importlib.import_module(mod)
            chk(mod, True, desc)
        except Exception as e:
            chk(mod, False, str(e)[:50])

    # Risk manager hızlı test
    try:
        from bot.risk_manager import calculate_position
        result = calculate_position(
            balance=1000, entry_price=2000, sl_price=1970,
            signal_score=7.0, open_count=0
        )
        chk("calculate_position() test", result["valid"],
            f"Lev={result.get('leverage','?')}x Qty={result.get('quantity',0):.4f}")
    except Exception as e:
        chk("calculate_position() test", False, str(e)[:50])


# ══════════════════════════════════════════════════════════════
#  8. VERİTABANI
# ══════════════════════════════════════════════════════════════
def check_database():
    section("8. VERİTABANI (SQLite)")
    try:
        import sqlite3
        os.makedirs("data/database", exist_ok=True)
        conn = sqlite3.connect("data/database/test_check.db")
        conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER, val TEXT)")
        conn.execute("INSERT INTO test VALUES (1, 'ok')")
        conn.commit()
        row = conn.execute("SELECT val FROM test").fetchone()
        conn.execute("DROP TABLE test")
        conn.close()
        chk("SQLite okuma/yazma", row and row[0] == "ok", "data/database/")

        from bot.position_manager import init_positions_db
        init_positions_db()
        chk("Bot pozisyon DB", True, "data/database/bot_positions.db")

    except Exception as e:
        chk("SQLite", False, str(e)[:50])


# ══════════════════════════════════════════════════════════════
#  9. EMAİL (opsiyonel — bağlantı testi)
# ══════════════════════════════════════════════════════════════
def check_email():
    section("9. EMAİL (Gmail SMTP)")
    sender   = os.getenv("EMAIL_SENDER", "")
    password = os.getenv("EMAIL_APP_PASSWORD", "")

    if not sender or sender == "your_gmail@gmail.com":
        print(f"  {warn('Email ayarlanmamış — .env dosyasına ekle')}")
        print(f"  {DM}  EMAIL_SENDER=senin@gmail.com{R}")
        print(f"  {DM}  EMAIL_APP_PASSWORD=16_karakter_uygulama_sifresi{R}")
        return

    try:
        import smtplib
        sys.stdout.write("  Gmail SMTP bağlantısı ... "); sys.stdout.flush()
        smtp = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        smtp.starttls()
        smtp.login(sender, password)
        smtp.quit()
        chk("Gmail SMTP login", True, sender)
    except smtplib.SMTPAuthenticationError:
        chk("Gmail SMTP login", False,
            "Kimlik doğrulama hatası — App Password doğru mu? (2FA açık olmalı)")
    except Exception as e:
        chk("Gmail SMTP", False, str(e)[:60])


# ══════════════════════════════════════════════════════════════
#  10. WEB SCRAPING
# ══════════════════════════════════════════════════════════════
def check_scraping():
    section("10. WEB SCRAPING")
    try:
        import requests
        from bs4 import BeautifulSoup

        # CoinGecko public API
        r = requests.get(
            "https://api.coingecko.com/api/v3/search/trending",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10
        )
        coins = r.json().get("coins", [])
        chk("CoinGecko Trending", len(coins) > 0, f"{len(coins)} trending coin")

        # CryptoPanic public
        r2 = requests.get(
            "https://cryptopanic.com/api/v1/posts/?auth_token=public&kind=news",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10
        )
        posts = r2.json().get("results", [])
        chk("CryptoPanic", len(posts) > 0, f"{len(posts)} haber")

    except Exception as e:
        chk("Web Scraping", False, str(e)[:50])


# ══════════════════════════════════════════════════════════════
#  SONUÇ ÖZETİ
# ══════════════════════════════════════════════════════════════
def print_summary():
    print(f"\n{'═'*60}")
    print(f"  {B}SONUÇ ÖZETİ{R}")
    print(f"{'═'*60}")

    total  = len(RESULTS)
    passed = sum(1 for _, s, _ in RESULTS if s)
    failed = total - passed

    print(f"  Toplam kontrol  : {total}")
    print(f"  {ok('')}Başarılı      : {GR}{passed}{R}")
    print(f"  {fail('')}Başarısız     : {RD}{failed}{R}")
    print()

    if failed > 0:
        print(f"  {B}Düzeltilmesi Gerekenler:{R}")
        for name, status, detail in RESULTS:
            if not status:
                print(f"  {RD}✗{R} {name}: {DM}{detail}{R}")

    print()
    if failed == 0:
        print(f"  {GR}{B}🏆 SİSTEM TAMAMEN HAZIR — Paper trading başlatabilirsin{R}")
        print(f"  {DM}  Sonraki adım: python paper_trader.py --start 100{R}")
    elif failed <= 2:
        print(f"  {YL}{B}⚠️  SİSTEM ÇOĞUNLUKLA HAZIR — Kritik olmayan eksikler var{R}")
        print(f"  {DM}  Yukarıdaki hataları düzelt, tekrar çalıştır{R}")
    else:
        print(f"  {RD}{B}❌ SİSTEM HAZIR DEĞİL — Kritik eksikler var{R}")
        print(f"  {DM}  pip install -r requirements.txt çalıştır, .env'i doldur{R}")

    print(f"{'═'*60}\n")

    print(f"  {B}Kurulum Adımları:{R}")
    steps = [
        ("✅" if all(s for n,s,_ in RESULTS if "Python" in n) else "○",
         "Python 3.9+ kurulu"),
        ("✅" if all(s for n,s,_ in RESULTS if "ccxt" in n or "pandas" in n or "yfinance" in n) else "○",
         "pip install -r requirements.txt"),
        ("✅" if any(s for n,s,_ in RESULTS if "API_KEY" in n or "env" in n.lower()) else "○",
         ".env dosyası dolduruldu"),
        ("✅" if any(s for n,s,_ in RESULTS if "Bakiye" in n) else "○",
         "Binance API key (Futures Trade izni)"),
        ("✅" if any(s for n,s,_ in RESULTS if "Gmail" in n) else "○",
         "Gmail App Password ayarlandı"),
        ("○", "python paper_trader.py --start 100  (Paper Trading)"),
        ("○", "2 hafta paper trade → sonuçları değerlendir"),
        ("○", "BOT_DRY_RUN=false → python bot/bot_main.py  (CANLI)"),
    ]
    for icon, step in steps:
        col = GR if icon == "✅" else DM
        print(f"  {col}{icon} {step}{R}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Alpha Bot — Sistem Kontrol")
    parser.add_argument("--quick", action="store_true", help="Sadece kritik kontroller")
    parser.add_argument("--fix",   action="store_true", help="Eksikleri otomatik düzelt")
    args = parser.parse_args()

    print(f"\n{'═'*60}")
    print(f"  {B}ALPHA İSTİHBARAT — SİSTEM KURULUM KONTROLÜ{R}")
    print(f"  {DM}{datetime.utcnow():%Y-%m-%d %H:%M UTC}{R}")
    print(f"{'═'*60}")

    if args.fix:
        print(f"\n  {CY}Otomatik düzeltme modunda...{R}")
        if not Path(".env").exists():
            import shutil
            shutil.copy(".env.example", ".env")
            print(f"  {ok('.env oluşturuldu — düzenlemeyi unutma')}")
        os.makedirs("data/database", exist_ok=True)
        os.makedirs("logs", exist_ok=True)
        print(f"  {ok('Klasörler oluşturuldu')}")

    check_python()
    check_libraries()
    check_env()
    check_binance()

    if not args.quick:
        check_bist()
        check_live_scan()
        check_bot()
        check_database()
        check_email()
        check_scraping()

    print_summary()


if __name__ == "__main__":
    main()
