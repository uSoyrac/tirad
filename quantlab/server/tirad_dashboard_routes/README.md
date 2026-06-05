# TIRAD canlı-dashboard ek route'ları (kaynak yedeği)

Bu dosyalar **sunucudaki** (`/root/tirad/dashboard2.py`, gunicorn `tirad-dash`)
versiyon-kontrolsüz Flask uygulamasına **ekli** (additive) olarak monte edilmiştir.
Buradaki kopya kaynak yedeğidir — sunucu sıfırlanırsa/`dashboard2.py` kaybolursa
yeniden uygulanabilsin diye.

## Dosyalar
- `rapor_route.py` — `/rapor` sekmesi: işlem geçmişi (hangi coin, hangi saatte al/sat,
  gerekçe), botların kâr sıralaması liste görünümü.
- `piyasa_route.py` — `/piyasa` sekmesi: geçmiş piyasa datası (4h fiyat + 4h/24h/7g
  değişim + SVG sparkline), cache parquet/CSV'den, kütüphane gerektirmez.
- `saglik_route.py` — `/saglik` sekmesi: canlı↔backtest sapma / overfit erken-uyarı
  (kasa <%85 → 🔴, drawdown backtest'i aşarsa → 🟡/🔴, <5 gün → 🟢 erken).
- `health_snapshot.py` — auth'suz cron job (`/etc/cron.d/tirad-health`, her 4 saatte
  `paper_runner.py`'den sonra): `paper/*.json` okur, `paper/health.json` + `health.log`
  yazar. `/saglik` ile aynı sağlık kuralları.

## Monte etme (sunucuda)
1. `rapor_route.py` / `piyasa_route.py` / `saglik_route.py` içerikleri `dashboard2.py`
   sonuna eklenir (`@app.route` + `@requires_auth` mevcut Flask `app`'ini kullanır).
2. Ana sayfanın nav linklerine `/rapor`, `/piyasa`, `/saglik` eklenir.
3. `health_snapshot.py` → `/root/tirad/health_snapshot.py`; cron satırı:
   `0 */4 * * * root cd /root/tirad && .venv/bin/python health_snapshot.py`.
4. `systemctl reload`/`pm2 restart tirad-dash`.

Her değişiklik additive ve `.bak_*` yedeğiyle yapıldı; gizli anahtar içermez.
