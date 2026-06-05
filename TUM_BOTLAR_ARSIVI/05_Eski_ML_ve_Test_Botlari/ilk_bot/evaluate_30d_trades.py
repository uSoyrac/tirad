import ccxt
import pandas as pd
from datetime import datetime, timedelta

exchange = ccxt.binance()

trades = [
    {"coin": "BTC", "date": "2026-05-12 16:00:00", "trend": "BULLISH", "l1": 78754.55, "l2": 78431.65, "sl": 77194.52},
    {"coin": "ETH", "date": "2026-05-04 08:00:00", "trend": "BULLISH", "l1": 2317.69, "l2": 2308.53, "sl": 2271.98},
    {"coin": "ETH", "date": "2026-05-26 16:00:00", "trend": "BEARISH", "l1": 2128.59, "l2": 2143.05, "sl": 2185.76},
    {"coin": "BNB", "date": "2026-05-16 04:00:00", "trend": "BULLISH", "l1": 664.75, "l2": 657.62, "sl": 644.48},
    {"coin": "XRP", "date": "2026-05-26 16:00:00", "trend": "BEARISH", "l1": 1.36, "l2": 1.37, "sl": 1.39}
]

print("="*50)
print(" 📈 GERÇEK PİYASA SONUÇLARI (30 GÜN) 📈")
print("="*50)

for t in trades:
    coin = t["coin"]
    start_date = pd.to_datetime(t["date"])
    
    # We fetch 200 hours (50 bars of 4H) after the signal
    ohlcv = exchange.fetch_ohlcv(f"{coin}/USDT", "4h", since=int(start_date.timestamp()*1000), limit=50)
    df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms')
    
    trend = t["trend"]
    l1 = t["l1"]
    l2 = t["l2"]
    sl = t["sl"]
    avg_entry = (l1 + l2) / 2
    
    # Define 2R target
    risk_dist = abs(avg_entry - sl)
    tp = avg_entry + (risk_dist * 2) if trend == "BULLISH" else avg_entry - (risk_dist * 2)
    
    filled = False
    result = "TIMEOUT"
    
    for _, row in df.iterrows():
        # skip the signal bar itself or wait for next bars
        if row['ts'] <= start_date: continue
        
        high, low = row["high"], row["low"]
        
        if trend == "BULLISH":
            if not filled and low <= l1:
                filled = True
            if filled:
                if low <= sl:
                    result = "STOP LOSS (-1R)"
                    break
                if high >= tp:
                    result = "TAKE PROFIT (+2R)"
                    break
        else: # BEARISH
            if not filled and high >= l1:
                filled = True
            if filled:
                if high >= sl:
                    result = "STOP LOSS (-1R)"
                    break
                if low <= tp:
                    result = "TAKE PROFIT (+2R)"
                    break
                    
    if not filled:
        result = "GIRILEMEDI (Fiyat emirleri almadan kacti)"
        
    print(f"{coin} ({trend}) - Sinyal: {t['date']}")
    print(f"Hedeflenen TP: {tp:.2f} | Durum: {result}\n")

