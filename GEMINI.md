# GEMINI.md — bu repoda nasıl çalışılır (agent giriş noktası)

Bu, çok-kollu, dürüst bir trading operasyonudur. **Başlangıç noktan:**

## 👉 BURADAN BAŞLA
1. **`uyg/06_HAZIR_BOTLAR_RAPORLAR/README.md`** — operasyonun haritası: iki ana bot
   (geçiş + funded-survival), panel-doğrulanmış optimal config'ler, edge hiyerarşisi.
2. **`uyg/06_HAZIR_BOTLAR_RAPORLAR/AGENT.md`** — çalıştırma & bakım + agent başlangıç rehberi.
3. **`uyg/Botlar/compound_engine.py`** — paylaşılan beyin (tüm botlar import eder). `PASS_CONFIGS`
   + `FUNDED_SURVIVAL` panel sayılarını kodlu tutar. `kill_switch` / `intraday_halt` / `profit_bank`.
4. **`uyg/06_HAZIR_BOTLAR_RAPORLAR/raporlar/`** — her iddianın arkasındaki backtest .md'leri.
5. Derin araştırma altyapısı: **`quantlab/`** (Py3.12 venv: `quantlab/.venv`). Raporları üreten
   scriptler `quantlab/scripts/run_*.py`; çalıştırma: `cd quantlab && .venv/bin/python scripts/...`.

## DOĞRULANMIŞ EDGE (kısa)
- ✅ Crypto **combo** (cross-sectional momentum + funding) — OOS ~1.85, DSR 1.00 / PBO 0.01. Ana edge.
- ✅ **US hisse momentum** — OOS 1.66, en kolay prop geçişi (Trade The Pool ~%66-73).
- ⚠️ FX carry modest (0.9). ⚠️ Trend rejim-bağımlı (ADX≥30 ile OOS +0.08, combo'nun YANINDA).
- ❌ Futures / forex-ex-carry / ML yön-tahmini: edge YOK.

## DEĞİŞMEZ DİSİPLİN (İHLAL ETME)
1. Canlı emir / gerçek-para öncesi **KULLANICI ONAYI**. Testnet/paper önce. Mainnet ayrı onay.
2. **Anahtarları asla repo'ya yazma** (yalnız server env / ephemeral). `.gitignore` korur; ihlal etme.
3. **≤¼-Kelly**, kill-switch + −%3 intraday-halt hep açık. Funded'da **compound YOK** (trailing floor).
4. Compound yalnız GERÇEK edge'i (combo/hisse) büyütür, trend'i DEĞİL.
5. **%100 geçiş İMKÂNSIZ** — dürüst tavan hissede ~%66-73, crypto'da ~%42-48. "Garanti kazanır" deme.
6. **Forward kanıt > backtest.** Backtest haircut'lı taban; gerçek = canlı-forward.

Detaylı operasyon: `uyg/06_HAZIR_BOTLAR_RAPORLAR/`. Proje çalışan-belleği: `quantlab/CLAUDE.md`.
