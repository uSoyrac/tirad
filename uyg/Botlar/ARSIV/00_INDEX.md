# 🤖 BOTLAR ARŞİVİ — Tüm Optimal Botların Tek Dizini

Bu dizin, iki sohbet + Gemini çalışmasının damıtılmış sonucudur. Her **doğrulanmış**
bot kendi klasöründe: `README.md` (strateji + nasıl çalıştırılır), `AGENT.md` (AI ajan
notları + dürüst durum), ve içinde **güncel test/optimallik sonuçları**.

Tüm sonuçlar **dürüst, OOS (out-of-sample), look-ahead'siz, maliyetler (komisyon+slippage
+funding+likidasyon) dahil**. ⚠️ Hepsi survivorship-capped (bugünün hayatta kalan
sembolleri) ve **PAPER-TRADE adayı — canlı sermaye DEĞİL.**

## ✅ Doğrulanmış optimal botlar (bu arşivde, çalıştırılabilir)

| # | Bot | Strateji | OOS 2025-26 | Durum |
|---|---|---|---|---|
| 01 | **`xasset`** ★★ | 3-kollu çapraz-varlık (kripto-trend + kripto-funding + ABD-momentum) | **Sharpe 2.40, MaxDD −7%** | EN İYİ; DSR 0.99 / PBO 0.03 geçti |
| 02 | `combo` ★ | Kripto trend Top-3 + funding-pozisyonlama | Sharpe 1.74 (WF-opt 2.25), MaxDD −14% | Doğrulandı |
| 03 | `funding` | Yüksek-funding short / düşük long (market-nötr) | Sharpe 1.31 (ortogonal) | Doğrulandı |
| 04 | `momentum` | 20 coin Top-3 cross-sectional momentum | Sharpe 1.12, win %41.8, +$70/işlem | Doğrulandı (en yüksek win-rate) |
| 05 | `paper` | Combo'nun ileriye-dönük paper-trade defteri | NAV $10k→$15.5k (516g), Sharpe 1.74 | Forward doğrulama aracı |

**Çalıştırma:** her klasördeki `calistir.py` → `quantlab/.venv/bin/python uyg/Botlar/ARSIV/01_xasset/calistir.py`
(quantlab paketini + yerel veriyi `uyg/src/` kullanır; ABD kolu yfinance+internet ister.)

## 📋 Kanıt zinciri (neden bunlar optimal)
- 15+ yaklaşım dürüstçe test edildi (trend, ML-tahmin, mean-reversion, sniper, Kelly,
  killzone, Fibonacci, türev/ivme...) — **çoğu OOS edge vermedi.**
- Tek dayanıklı edge: **yapısal çeşitlendirme** (ortogonal kollar, √N breadth) — yeni sinyal değil.
- Overfitting kapısı (Deflated Sharpe 0.99, PBO 0.03) geçildi → combo/xasset edge'i şanslı grid-seçimi DEĞİL.
- Raporlar: `quantlab/reports_out/` (bakeoff, pbo, levers, stocks, combo, carry...).

## ⚠️ Diğer botlar (Gemini/Antigravity — DENETLENDİ, bu arşivde DEĞİL)
Bunlar `origin/claude/compound-engine-v63` branch'inde (`01_Asimetrik_Sniper` ... `10_Prop_Firm`).
Bizim dürüst harness'ımızda denetlendiler — **deploy edilmemeli:**
- Asimetrik Sniper (TP10/SL2, 10x): dürüst testte **negatif-EV, RoR %67**; 10x kill-switch'i patlatıp duruyor.
- Dinamik Kelly (%60 notional): risk-of-ruin yüksek; backtestleri **likidasyon/gap modellemiyor** + top-X% eşiğinde **look-ahead** var.
- `bot_kararli/dengeli/optimal/quantpro/rejim` (XGBoost gate + TP5/SL2.5): XGBoost kapısı bizim purged-CV testimizde **AUC ~0.52 = yazı-tura**; gate portföyü bozuyor. Kendi README'lerindeki "paper-trade first, deflated Sharpe ~%31" uyarıları yerinde.

**Özet:** En optimal ve doğrulanmış sistem **`01_xasset`** (Sharpe 2.40). İlk iş: paper-trade ile ileriye-dönük doğrulama.
