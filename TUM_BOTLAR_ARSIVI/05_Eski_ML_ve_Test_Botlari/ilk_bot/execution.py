import ccxt
import time
import os
import json

def place_binance_orders(symbol, l1, l2, sl, tp, risk_amount):
    """
    GERÇEK BINANCE API BAĞLANTISI (EXECUTION ENGINE)
    Not: Güvenlik gereği API keyler ortam değişkenlerinden (Environment Variables) çekilir.
    """
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    
    if not api_key or not api_secret:
        print("HATA: Binance API Key bulunamadı! Lütfen ortam değişkenlerini ayarlayın.")
        print("Test Modunda (Dry-Run) çalıştırılıyor...\n")
        print(f"[TEST EMİRLERİ] {symbol}:")
        print(f"  > Limit 1: {l1} | Limit 2: {l2}")
        print(f"  > Stop Loss: {sl} | Take Profit: {tp}")
        return False
        
    try:
        # Binance Futures veya Spot Bağlantısı
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'} # Kaldıraçlı işlemler için
        })
        
        # Piyasa fiyatını çek
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        # Risk Miktarına Göre Pozisyon Büyüklüğü Hesaplama (Position Sizing)
        avg_entry = (l1 + l2) / 2
        risk_per_coin = abs(avg_entry - sl)
        
        if risk_per_coin == 0:
            return False
            
        qty = risk_amount / risk_per_coin
        half_qty = qty / 2
        
        print(f"Borsaya Bağlanıldı! {symbol} Güncel Fiyat: {current_price}")
        
        # Gerçek Borsaya Emirleri Gönder
        # 1. Limit Order 1
        order1 = exchange.create_limit_buy_order(symbol, half_qty, l1) if avg_entry > sl else exchange.create_limit_sell_order(symbol, half_qty, l1)
        
        # 2. Limit Order 2
        order2 = exchange.create_limit_buy_order(symbol, half_qty, l2) if avg_entry > sl else exchange.create_limit_sell_order(symbol, half_qty, l2)
        
        # 3. Stop Loss & Take Profit (Conditional Orders)
        # Note: Bu kısım CCXT'nin gelişmiş conditional emirlerine veya botun kendi websocket takibine devredilir.
        print(f"✅ Başarılı! Emirler Borsaya İletildi.")
        print(f"Emir ID 1: {order1['id']}")
        print(f"Emir ID 2: {order2['id']}")
        return True
        
    except Exception as e:
        print(f"Borsa Emri Gönderilirken Kritik Hata: {str(e)}")
        return False

if __name__ == "__main__":
    print("Execution Engine Hazır. Test emri gönderiliyor (API Key Yoksa Dry-Run çalışır)...")
    place_binance_orders("BTC/USDT", 78754.55, 78431.65, 77194.52, 81000.00, 10.0)
