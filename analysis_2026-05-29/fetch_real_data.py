"""
fetch_real_data.py
==================
KENDİ MAKİNENİZDE çalıştırın (borsa erişimi açıkken). ETH/USDT 1h son N ay
veriyi çekip 'data_eth_1h.csv' olarak kaydeder. Sonra signal_lab.py ve
diğer scriptler bu GERÇEK veriyi otomatik kullanır.

  pip install ccxt pandas
  python fetch_real_data.py            # varsayılan: son 4 ay, Binance futures

Not: Bu repo çalıştırıldığı bulut ortamında borsalar 'allowlist dışı'
olduğundan veri çekilemiyor; bu yüzden bu adımı siz çalıştırmalısınız.
"""
import sys, time
import pandas as pd

try:
    import ccxt
except ImportError:
    print("ccxt yok: pip install ccxt"); sys.exit(1)

SYMBOL = "ETH/USDT"
TF = "1h"
MONTHS = 4
EXCHANGES = ["binanceusdm", "binance", "bybit", "okx", "kucoin"]


def fetch(symbol=SYMBOL, tf=TF, months=MONTHS):
    need = months * 30 * 24
    since_ms = ccxt.binance().milliseconds() - need * 3600_000
    last_err = None
    for name in EXCHANGES:
        try:
            ex = getattr(ccxt, name)({"enableRateLimit": True})
            rows, since = [], since_ms
            while True:
                batch = ex.fetch_ohlcv(symbol, tf, since=since, limit=1000)
                if not batch: break
                rows += batch
                since = batch[-1][0] + 3600_000
                if len(batch) < 1000 or len(rows) >= need + 50: break
                time.sleep(ex.rateLimit / 1000)
            df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df.drop_duplicates("timestamp").set_index("timestamp")
            df = df.iloc[:-1]                 # forming bar at — anti-repaint
            df.tail(need).to_csv("data_eth_1h.csv")
            print(f"[OK] {name}: {len(df)} bar -> data_eth_1h.csv "
                  f"({df.index[0]} → {df.index[-1]})")
            return df
        except Exception as e:
            last_err = f"{name}: {str(e)[:80]}"
            print("  dene başarısız:", last_err)
    print("HATA: hiçbir borsadan veri alınamadı."); print(last_err)


if __name__ == "__main__":
    fetch()
