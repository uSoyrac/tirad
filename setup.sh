#!/bin/bash
# Alpha İstihbarat Sistemi — Kurulum scripti
set -e

echo "=============================="
echo "Alpha İstihbarat Sistemi Kurulum"
echo "=============================="

# Python versiyonu kontrol
python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python: $python_version"

if [[ $(python3 -c 'import sys; print(1 if sys.version_info >= (3,11) else 0)') == "0" ]]; then
    echo "UYARI: Python 3.11+ önerilir. Mevcut: $python_version"
fi

# Virtual environment
if [ ! -d "venv" ]; then
    echo "Virtual environment oluşturuluyor..."
    python3 -m venv venv
fi

source venv/bin/activate

# Bağımlılıklar
echo "Bağımlılıklar yükleniyor..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# spaCy İngilizce model
echo "spaCy İngilizce model yükleniyor..."
python -m spacy download en_core_web_sm -q || echo "spaCy modeli atlandı (opsiyonel)"

# .env oluştur
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "=== .env dosyası oluşturuldu ==="
    echo "Lütfen .env dosyasını API anahtarlarınızla doldurun:"
    echo "  ANTHROPIC_API_KEY=..."
    echo "  BINANCE_API_KEY=..."
    echo "  EMAIL_SENDER=..."
    echo "  EMAIL_APP_PASSWORD=..."
    echo ""
fi

# Playwright kurulum (opsiyonel)
echo "Playwright kurulumu (web scraping için)..."
python -m playwright install chromium --with-deps 2>/dev/null || echo "Playwright atlandı (opsiyonel)"

echo ""
echo "=============================="
echo "Kurulum tamamlandı!"
echo ""
echo "Kullanım:"
echo "  source venv/bin/activate"
echo "  python main.py            # Tek tarama"
echo "  python main.py --loop     # Sürekli tarama"
echo "  python main.py --backtest # Backtest"
echo "  python main.py --status   # Son sinyaller"
echo "  python main.py --symbol BTC/USDT  # Tek sembol"
echo "=============================="
