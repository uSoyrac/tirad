# 🏛️ TÜM BOTLAR — MASTER DİZİN (BURADAN BAŞLA)

Tüm projenin (iki Claude sohbeti + Gemini/Antigravity) ulaştığı **en optimal botların
tamamı tek yerde.** İki aile var; ikisi de PAPER-TRADE adayı, canlı sermaye DEĞİL.

> **Dürüstlük notu:** Rakamlar iki farklı motordan geliyor. (A) ailesi Gemini'nin kendi
> backtest motoru/varsayımlarıyla (data_v63); (B) ailesi `quantlab`'in look-ahead'siz,
> likidasyon+gap+funding+komisyon dahil harness'ıyla + overfitting kapısı (Deflated
> Sharpe/PBO). Aşağıda her ikisini de dürüstçe gösteriyorum — kör deploy etme.

---

## 🅰️ KİŞİSEL FON & PROP FİRMA BOTLARI (Gemini) — `01..10_*.py`
Gemini'nin kendi raporladığı sonuçlar. README.md'de detaylı.

| # | Bot | Amaç (Gemini) |
|---|---|---|
| 01 | `01_Asimetrik_Sniper_Bot` | Yüksek-kazanç sniper, Kelly agresif giriş |
| 02 | `02_Guvenli_Hasat_Maas_Botu` | Aylık nakit (maaş) çekimi, defansif |
| 03 | `03_Manuel_Sinyal_Jeneratoru` | Manuel giriş için sinyal asistanı |
| 04 | `04_Optimal_Sniper_Harvest` | Sniper + kâr-çekimi, dengeli bileşik |
| 05 | `05_Dinamik_Kelly_Hasat_Botu` | Kazanınca artır/kaybedince azalt (anti-martingale) |
| 06 | `06_Prop_Firm_5K_Kaplumbaga` | 5K −%3 limit, Kelly 0.8x kilitli, yavaş-güvenli |
| 07 | `07_Prop_Firm_5K_Yuksek_Kaldirac` | 5K −%5, 1.5x Kelly, agresif |
| 08 | `08_Prop_Firm_5K_Agresif_RR` | Sabit R/R (−%2/+%4) |
| 09 | `09_Prop_Firm_5K_Kutsal_Kase_Hibrid` 👑 | −%1 sabit risk, patlamayı imkânsız kılan hibrid |
| 10 | `10_Prop_Firm_50K_Son_6_Ay` 💎 | Hibrid'in 50K versiyonu, son-6-ay survivor |
| 11 | `11_Live_MT5_Execution_Bot` 🔴 | **CANLI MT5 emir-yürütme botu** — gerçek hesapta emir gönderir |

> **🔴 BOT 11 — CANLI YÜRÜTME UYARISI:** Bu bot backtest değil, **gerçek MetaTrader5
> hesabında canlı emir gönderir.** quantlab disiplinine göre canlı sermaye için ÖNCE: (1)
> forward paper-trade'in backtest'i tuttuğunu kanıtla, (2) survivorship'i düzelt, (3) küçük
> sermaye + sıkı risk limiti. Doğrulanmamış bir edge'i canlı çalıştırmak parayı yakar. Test
> edilmeden ÇALIŞTIRMA.
>
> **⚠️ quantlab harness denetimi (A ailesi):** Bu botların çekirdeği asimetrik TP/SL +
> XGBoost "top-%5" kapısı. Bizim look-ahead'siz, likidasyon-modelleyen harness'ımızda:
> asimetrik sniper **negatif-EV (RoR %67)**, 10x kaldıraç kill-switch'i patlatıyor; XGBoost
> kapısı **purged-CV AUC ~0.52 (yazı-tura)**; backtestler **likidasyon/gap modellemiyor** ve
> top-X% eşiğinde **look-ahead** var. Gemini'nin kendi README'sindeki "deflated Sharpe ~%31,
> paper-trade first" uyarısı yerinde. → **Kör deploy etme; önce paper.**

---

## 🅱️ QUANTLAB DOĞRULANMIŞ BOTLAR (Claude) — `bot_*.py` + `ARSIV/`
Look-ahead'siz, tüm maliyetler dahil, OOS (2025-26), overfitting kapısı geçildi.

| Bot | Strateji | OOS Sharpe | Durum |
|---|---|---|---|
| **`bot_xasset.py`** ★★ | 3-kollu çapraz-varlık (kripto-trend + funding + ABD-momentum) | **2.40** (MaxDD −7%) | EN İYİ; DSR 0.99/PBO 0.03 geçti |
| `bot_combo.py` ★ | kripto trend + funding | 1.74 (WF-opt 2.25) | doğrulandı |
| `bot_funding.py` | market-nötr funding-pozisyonlama | 1.31 | ortogonal kol |
| `bot_xsec_momentum.py` | Top-3 cross-sectional momentum | 1.12 (win %41.8) | en yüksek win-rate |
| `bot_paper.py` | ileriye-dönük paper defteri | NAV $10k→$15.5k | forward doğrulama |

Detaylı per-bot README + AGENT.md + sonuçlar: **`ARSIV/01_xasset/` ... `ARSIV/05_paper/`**
(her birinde `calistir.py` çalıştırıcı). Çalıştırma:
`quantlab/.venv/bin/python uyg/Botlar/ARSIV/01_xasset/calistir.py`

---

## 🎯 NİHAİ HÜKÜM
- **En titiz-doğrulanmış, dayanıklı, dürüst sistem: `bot_xasset` (OOS Sharpe 2.40).**
  Tek edge'i kanıtlanmış (DSR 0.99, PBO 0.03), kollar ortogonal, çapraz-varlık breadth.
- A ailesi (prop/sniper) görsel olarak etkileyici ama harness denetimi risk gösteriyor →
  paper-trade ile ileriye doğrula, kör güvenme.
- **Hepsi survivorship-capped ve PAPER-TRADE adayı.** İlk gerçek iş: forward paper doğrulama.
