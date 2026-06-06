#!/usr/bin/env python3
"""
CANLI MT5 EXECUTION BOTU (Live Market)
Model: Kutsal Kâse Hibrid (Sabit R/R, -%1 Risk, Zombi Sendromsuz)

Bu bot simülasyon DEĞİLDİR. Gerçek MetaTrader 5 (MT5) Prop Firması hesabınıza
bağlanıp, sinyal üreterek canlı piyasada alım/satım (Execution) yapar.
"""
import time
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# --- ⚙️ KULLANICI / PROP FİRMASI AYARLARI ---
LOGIN = 12345678              # MT5 Hesap Numaran (Prop Firm)
PASSWORD = "YOUR_PASSWORD"    # MT5 Şifren
SERVER = "PropFirm-Server"    # Prop Firmasının Sunucu Adı (Örn: FTMO-Server)
SYMBOL = "EURUSD"             # İşlem yapılacak parite
TIMEFRAME = mt5.TIMEFRAME_H1  # Zaman dilimi

START_BALANCE = 50000.0       # Sınavın başlangıç bakiyesi
PAYOUT_THRESHOLD = 2500.0     # Kâr Çekim (Vur-Kaç) Hedefi ($2500 Kâr)

# --- 🎯 STRATEJİ AYARLARI (KUTSAL KÂSE) ---
RISK_PCT = 0.01               # İşlem başına riske edilecek tutar (%1)
SL_PIPS = 20.0                # Stop Loss Mesafesi (Pip cinsinden)
RR_RATIO = 2.0                # Risk/Ödül Oranı (1:2)
TP_PIPS = SL_PIPS * RR_RATIO  # Take Profit Mesafesi

def connect_mt5():
    """MetaTrader 5 terminaline bağlanır."""
    print("🔄 MT5 Terminaline bağlanılıyor...")
    if not mt5.initialize(login=LOGIN, server=SERVER, password=PASSWORD):
        print(f"❌ MT5 Bağlantı Hatası! Hata Kodu: {mt5.last_error()}")
        return False
    print("✅ MT5 Bağlantısı Başarılı!")
    return True

def get_live_signal():
    """
    Geçmişte eğittiğimiz XGBoost 'smartmoney_sigs.pkl' modelini 
    canlı verilere uygulayarak sinyal üretir.
    (Bu örnekte yer tutucu - Canlı modelinle değiştirilecek)
    """
    # TODO: XGBoost clf.predict() fonksiyonunu buraya entegre et
    # 1 = BUY, -1 = SELL, 0 = BEKLE
    # Test için şimdilik rastgele sinyal:
    signal = np.random.choice([1, -1, 0], p=[0.2, 0.2, 0.6])
    return signal

def calculate_lot_size(equity, sl_pips, symbol):
    """
    Kutsal Kâse Formülü: Anlık bakiyenin TAM OLARAK %1'ini riske edecek Lot miktarını hesaplar.
    Ne eksik ne fazla, her zaman sabit Risk/Ödül matematiğini korur.
    """
    risk_amount = equity * RISK_PCT
    
    # Parite bilgisini al (Tick size, point value vb.)
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"❌ {symbol} paritesi bulunamadı!")
        return 0.0
        
    # Pip değerini dolara çevirip lot hesaplama (Örnek standart formül)
    tick_value = symbol_info.trade_tick_value
    tick_size = symbol_info.trade_tick_size
    pip_value = tick_value * (0.0001 / tick_size) # EURUSD gibi standart Forex için
    
    # Lot başına risk edilen tutar
    risk_per_lot = sl_pips * pip_value
    
    # Hesaplanmış Lot miktarı
    lot_size = risk_amount / risk_per_lot
    
    # Borsanın kabul ettiği adım (step) değerine yuvarla (örn: 0.01)
    step = symbol_info.volume_step
    lot_size = round(lot_size / step) * step
    
    # Minimum ve Maksimum lot limitlerini kontrol et
    lot_size = max(lot_size, symbol_info.volume_min)
    lot_size = min(lot_size, symbol_info.volume_max)
    
    return lot_size

def execute_trade(signal_type, lot, symbol):
    """MT5 üzerinden gerçek emri borsaya iletir."""
    symbol_info = mt5.symbol_info(symbol)
    point = symbol_info.point
    price = mt5.symbol_info_tick(symbol).ask if signal_type == 1 else mt5.symbol_info_tick(symbol).bid
    
    # SL ve TP Fiyatlarını Hesapla
    if signal_type == 1: # BUY
        order_type = mt5.ORDER_TYPE_BUY
        sl = price - (SL_PIPS * 10 * point) # 1 pip = 10 points
        tp = price + (TP_PIPS * 10 * point)
    else: # SELL
        order_type = mt5.ORDER_TYPE_SELL
        sl = price + (SL_PIPS * 10 * point)
        tp = price - (TP_PIPS * 10 * point)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot),
        "type": order_type,
        "price": price,
        "sl": float(sl),
        "tp": float(tp),
        "deviation": 20,
        "magic": 999999, # Botun imzası (Kutsal Kâse Kimliği)
        "comment": "Kutsal_Kase_Hybrid",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    print(f"📡 Emir Gönderiliyor... Yön: {'BUY' if signal_type == 1 else 'SELL'} | Lot: {lot}")
    result = mt5.order_send(request)
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ Emir Başarısız! Hata: {result.retcode} - {result.comment}")
    else:
        print(f"✅ Emir Başarıyla İletildi! Bilet No: {result.order}")

def run_live_bot():
    if not connect_mt5():
        return

    print("\n" + "="*70)
    print(" 🤖 KUTSAL KÂSE MT5 CANLI İŞLEM BOTU (LIVE MARKET) BAŞLATILDI 🤖")
    print("="*70)

    try:
        while True:
            # 1. Anlık Bakiye (Equity) Kontrolü
            account_info = mt5.account_info()
            if account_info is None:
                print("❌ Hesap bilgisi alınamadı. Yeniden deneniyor...")
                time.sleep(10)
                continue
                
            equity = account_info.equity
            balance = account_info.balance
            open_positions = mt5.positions_get(symbol=SYMBOL)
            
            print(f"📊 [Canlı Durum] Bakiye: ${balance:,.2f} | Equity: ${equity:,.2f}")
            
            # 2. Vur-Kaç (Payout) Hedefine Ulaşıldı Mı? Güvenlik Kilidi!
            if equity >= START_BALANCE + PAYOUT_THRESHOLD:
                print("\n" + "🚨"*20)
                print(f"🎉 VUR-KAÇ HEDEFİNE ULAŞILDI! (Anlık Equity: ${equity:,.2f})")
                print("🔒 Bot kendini kilitledi. Lütfen Prop Firması panelinden paranı ÇEK (PAYOUT)!")
                print("🚨"*20 + "\n")
                break # Döngüden çık, işlemleri tamamen durdur.
                
            # 3. Zaten açık bir işlem var mı? (Günde veya anda 1 işlem kotası)
            if open_positions is not None and len(open_positions) > 0:
                print("⏳ Zaten açık bir pozisyon var. Sonuçlanması bekleniyor...")
                time.sleep(300) # 5 dakika bekle
                continue
                
            # 4. XGBoost Canlı Sinyal Sorgusu
            signal = get_live_signal()
            
            # 5. Sinyal varsa İşleme Gir
            if signal in [1, -1]:
                # Tam olarak -%1 risk için lot miktarını hesapla
                lot = calculate_lot_size(equity, SL_PIPS, SYMBOL)
                if lot > 0:
                    execute_trade(signal, lot, SYMBOL)
            else:
                print("😴 Piyasada fırsat yok. Sinyal bekleniyor...")
                
            # Belirli aralıklarla piyasayı tara (Örn: 15 dakikada bir)
            time.sleep(900)

    except KeyboardInterrupt:
        print("\n🛑 Bot kullanıcı tarafından durduruldu.")
    finally:
        mt5.shutdown()
        print("🔌 MT5 Bağlantısı Kapatıldı.")

if __name__ == "__main__":
    run_live_bot()
