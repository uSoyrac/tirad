# EMIR — Gerçek Veri Bulguları (2026-05-30)

> ⚠️ **DÜZELTME NOTU:** Bu dosyanın ilk sürümünde (commit 01d8830) CI çıktısını tam
> okumadan **yanlış sayılar** yazdım (WR %34, −0.21R, ORP→$0). O rakamlar GEÇERSİZ.
> Aşağıdakiler CI'ın `emir/results_real.md` / `run_log.txt` dosyalarındaki **gerçek**
> sonuçlardır. Hata bana ait; kayda geçiyorum (no hayal kuralı kendime de işler).

Veri GitHub Actions runner'ında **canlı Binance'ten** çekildi (geo-block olmadı).
Son 3 ay · 4H · BTC/ETH/SOL/BNB/XRP · ~540 mum/coin. Üretici: `emir/fetch_and_backtest.py`.

## Gerçek Sonuç (clean-room SMC baseline, AI filtresi YOK)
| Metrik | Gerçek |
|---|---|
| Dolan işlem | 83 |
| TP / SL / Timeout | 27 / 56 / 0 |
| Win Rate (fee'li) | **%32.5** |
| Beklenti | **+0.050 R/işlem** |
| Toplam | **+4.11 R** |
| Max ardışık kayıp | **10** |
| **ORP $100 →** | **$66.44 (−%33.6, maxDD %81.2)** |
| Sabit %4 risk → | **$95.88 (−%4.1)** |

## En Kritik Bulgu: ORP edge'i YOK ETTİ
- Ham strateji 3 ayda **+4.11 R** üretti (hafif pozitif — çünkü TP=2R, WR %32.5
  ile beklenti sıfıra yakın artı). Yani sinyal "tam çöp" değil, breakeven civarı.
- **AMA** 10 ardışık kayıp geldiğinde ORP'nin deficit-recovery + %20 cap mekanizması
  kasayı **%81 drawdown'a** soktu ve +4.11R'lik ham kazancı **−%33.6 zarara** çevirdi.
- Aynı işlemler **sabit %4 risk** ile sadece **−%4.1**'di.
- **Sonuç:** ORP "exponansiyel büyüme / risksiz / deficit her zaman siler" iddiası
  GERÇEK veride ÇÜRÜK. ORP, breakeven bir edge'i felakete dönüştüren bir **risk
  yükselticidir**. AGENT.md Faz 4 acilen düzeltilmeli.

## Üç Kanıtlanmış Gerçek (özet)
1. **XGBoost beyni mock veriyle eğitilmiş** (seed=42, label 268/268). %75 WR
   döngüsel/geçersiz. → `emir/train_xgb_real.py` ile gerçek veriyle yeniden eğitim
   CI'da koşuyor.
2. **Ham SMC baseline gerçek veride breakeven** (+0.05R, WR %32.5). AI filtresi
   olmadan edge zayıf.
3. **ORP, kanıtlanmış biçimde zarar büyütücü** (−%4 → −%34, %81 DD). Devre kesici
   şart.

## Dürüstlük Sınırı
- Bu baseline tam `score_slice_v2` motoru DEĞİL ve XGBoost filtresi (>0.60) burada
  UYGULANMADI. Tam sistem (gerçek motor + gerçek-eğitimli beyin) ayrı CI işinde
  (`emir-train-xgb.yml`) ölçülüyor.

## Sıradaki Adımlar
1. ✅ Çalışıyor: XGBoost'u gerçek veriyle eğit (CI) → gerçek WR + CI.
2. **ORP devre kesici:** N ardışık kayıpta riski base'e sabitle / döngüyü dondur;
   `dd_scaling=True` + recovery_factor>1.0'ı gerçek seride ölç.
3. Tam motor + gerçek beyin + düzeltilmiş ORP'yi birlikte backtest et.
4. Edge gerçek veride net pozitif değilse canlıya GEÇME.
