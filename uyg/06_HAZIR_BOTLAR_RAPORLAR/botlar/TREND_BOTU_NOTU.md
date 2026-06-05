# TREND BOTU (Binance trend-kolu) — "tirad" + ADX≥30 geliştirmesi

**Çalışan bot:** `/root/tirad/uyg/src/live_bot.py` (PM2: tirad-bot, Binance Futures testnet).
Strateji: çok-coin 4H Donchian(40)+Supertrend(10,3) agreement + BTC-200EMA hizalama +
rejim-gate(≥2) + ML meta-label + fractional-Kelly, long+short.

**Doğrulanmış GELİŞTİRME (uygula):** per-coin **ADX≥30 filtresi** — chop'u eler.
OOS realized: baz −0.02R → ADX≥30 ile **+0.08R** (run_trend_filtered.py). Uygulama: decide()'a
`adx(df,14)[-1] >= 30` koşulu ekle (veya env BOT_ADX_MIN=30).

**KULLANMA:** hızlı-TP (1.5R) istifi ZARAR verdi (kazananı keser; run_trend_improved.md). Sabit
TP 2.75R + ADX≥30 en iyisi.

**ROL:** combo'nun YERİNE değil YANINDA — trend-yıllarında (2021-23, 2024, 2026) ekstra yakalar,
chop'ta (2025) küçük kalır. Opportunistic trend-kolu. Rejim-bağımlı; tek başına combo'yu geçmez
ama çoklu-bot vizyonunda trend-yakalama armı.
