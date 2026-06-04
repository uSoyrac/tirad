# AGENT.md — 05_paper

**Ne:** Combo'nun ileriye-dönük paper-trade defteri (NAV ledger + güncel hedefler).
Kanonik: `uyg/Botlar/bot_paper.py`, çekirdek `quantlab/paper/combo_book.py`. CANLI EMİR YOK.

**Durum:** Backtest'le faithful (OOS Sharpe 1.74, NAV $10k→$15.5k/516g). Ledger:
`quantlab/reports_out/paper_book.json`.

**YAP:** `bot_xasset`'e genişlet (3-kollu defter); gerçek forward kayıt için auto-fetch
(ccxt/yfinance taze bar) + zamanlama (cron/4h) bağla. **YAPMA:** canlı emir gönderme —
kullanıcı onayı + forward paper'ın tutması + survivorship düzeltmesi şart. Bu, canlıdan
önceki kapı.
