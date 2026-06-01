# VDS Dağıtımı — periyodik tarayıcı

Tarayıcı (`scripts/scan_once.py`) bir sembol listesini tarar, geçerli
setup'ları stdout'a ve `output/scan-YYYY-MM-DD.log` dosyasına yazar.
**Sadece Python stdlib gerekir** — `pip install` yok. Tek koşul: VDS'nin
çıkış ağı açık olmalı (Binance public API'ye erişebilmeli).

## 1. Kodu çek

```bash
cd ~ && git clone <repo-url> tirad
cd tirad/price
git checkout claude/pensive-shannon-BpUKs
```

## 2. Elle test et (servise geçmeden önce)

```bash
PA_SYMBOLS="BTC/USDT,ETH/USDT,SOL/USDT" PA_DATA=1 python3 scripts/scan_once.py
```

Ağ açıksa geçerli setup'ları (veya "İşlem yok") görürsün. `Host not in
allowlist` / `Forbidden` görürsen VDS'nin çıkışı da kısıtlı demektir.

## 3a. systemd ile (önerilen)

`deploy/pa-scan.service` içindeki `User`, `WorkingDirectory` ve
`Environment` satırlarını düzenle, sonra:

```bash
sudo cp deploy/pa-scan.service /etc/systemd/system/
sudo cp deploy/pa-scan.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pa-scan.timer

# durum / log
systemctl list-timers pa-scan.timer
journalctl -u pa-scan.service -f
```

Aralığı `pa-scan.timer` içindeki `OnUnitActiveSec` ile değiştir (varsayılan
15 dk).

## 3b. cron ile (alternatif)

```bash
crontab -e
# deploy/crontab.example içeriğini yapıştır, yolları düzenle
```

## Ortam değişkenleri

| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `PA_SYMBOLS` | BTC/ETH/SOL USDT | virgüllü sembol listesi |
| `PA_ENTRY_TF` | `1h` | giriş zaman dilimi |
| `PA_HTF` | `4h` | üst-TF filtresi (`none` = kapalı) |
| `PA_LIMIT` | `300` | çekilecek mum sayısı |
| `PA_DATA` | `0` | `1` → geçerli setup'lara BÖLÜM 2 verisi ekle |
| `PA_PORTFOLIO` | — | pozisyon büyüklüğü hesabı için portföy |
| `PA_LOG_DIR` | `price/output` | log klasörü |

## Güvenlik notu

Bu tarayıcı yalnızca **public, anahtarsız** veri çeker — API anahtarı
gerekmez, emir göndermez. Bildirim (Telegram vb.) eklenecekse token'lar
VDS'de `.env` veya systemd `EnvironmentFile=` ile tutulmalı, repoya
girmemeli.
