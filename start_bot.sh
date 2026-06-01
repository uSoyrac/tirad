#!/bin/bash
# Alpha İstihbarat V22 (Hibrit) Başlatma Betiği

cd "$(dirname "$0")"

# Sanal ortamı aktif et
source venv/bin/activate

echo "🚀 Alpha İstihbarat Botu (Paper Trader) Başlatılıyor..."
echo "Yapay Zeka: V21 XGBoost Aktif"
echo "Mimari: Claude OOP + \$50.000 Likidite Duvarı"

# Arka planda loglayarak çalıştır
nohup python paper_trader.py > logs/bot_live.log 2>&1 &

echo "✅ Bot arka planda çalışmaya başladı!"
echo "Logları izlemek için: tail -f logs/bot_live.log"
