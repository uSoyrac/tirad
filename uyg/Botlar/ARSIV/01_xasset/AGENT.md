# AGENT.md — 01_xasset

**Ne:** 3-kollu çapraz-varlık kitabı (kripto-trend + kripto-funding + ABD-momentum),
inverse-vol ağırlık. Projenin en iyi, doğrulanmış sistemi. Kanonik kod:
`uyg/Botlar/bot_xasset.py`. Çekirdek mantık `quantlab/` paketinde (portfolio, carry,
combine, orchestrator).

**Durum:** OOS Sharpe 2.40, MaxDD −7%. Overfitting kapısını geçti (DSR 0.99, PBO 0.03).
PAPER-TRADE adayı — canlı DEĞİL.

**Bir agent ne YAPMALI:**
- İleriye-dönük paper doğrulama için `05_paper` defterini bu kitaba genişlet.
- Survivorship'i düzelt: point-in-time evren (ölen coinler + S&P constituents).
- 4. ortogonal kol araştır (equity value/low-vol faktörü — ABD funding-analog'u).

**Bir agent ne YAPMAMALI:**
- Sinyal-tahmin ML gate'i EKLEME — purged-CV'de AUC ~0.52 (yazı-tura), portföyü bozuyor.
- Kaldıracı abartma — full-Kelly f*~17.8x fat-tail'de iflas; tavan ≤¼-Kelly (−24% DD).
- Mutlak Sharpe'a güvenip canlı sermaye koyma — survivorship düzeltilene + forward paper
  tutana kadar HAYIR. Canlı emir için kullanıcıdan açık onay şart.

**Kanıt:** `quantlab/reports_out/{levers,pbo,stocks,combo}.md`, `quantlab/CLAUDE.md`.
