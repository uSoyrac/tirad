"""
audit_report_math.py
====================
Raporun KENDİ İÇİNDEKİ matematiksel iddialarını denetler. (Veriden bağımsız;
saf cebir/olasılık.) Hedef: rapor doğru veriye dayansa bile mantık hataları
var mı?
"""
import numpy as np

line = "─" * 70


def kelly_check():
    print(line); print("1) KELLY KRİTERİ İDDİASI (rapor §7.1)")
    print(line)
    p, q, b = 0.90, 0.10, 2.35
    f = (p * b - q) / b
    print(f"  Rapor formülü f* = (p·b − q)/b = ({p}·{b} − {q})/{b} = {f:.3f} = %{f*100:.1f}")
    print(f"  -> Raporun verdiği %85.7 ARİTMETİK OLARAK DOĞRU.")
    print()
    print("  ANCAK iki ciddi yorum hatası var:")
    print("  (a) Bu Kelly, 'tek kazanç/kayıp' (Bernoulli) modeli içindir. Botun")
    print("      kademeli TP'leri (R'leri farklı 3 çıkış) ile uyumsuz; b=2.35")
    print("      ağırlıklı ortalama R sayılıp tek-sonuç gibi kullanılmış -> yanlış model.")
    print("  (b) %85.7 risk, p=%90 kazanma 'GERÇEK' ise geçerli. p hatalıysa")
    print("      (look-ahead ile şişmişse) Kelly de tamamen çöker.")
    # Kelly'nin p'ye duyarlılığı
    print()
    print("  Kelly'nin gerçek kazanma oranına duyarlılığı (b=2.35 sabit):")
    for pp in [0.90, 0.75, 0.60, 0.55, 0.50, 0.45]:
        ff = (pp * b - (1 - pp)) / b
        tag = "  <- breakeven altı, KAYBETTİRİR" if ff <= 0 else ""
        print(f"    p=%{pp*100:.0f} -> f*=%{ff*100:.1f}{tag}")
    print("  Yorum: p %90'dan %55'e düşerse Kelly %36'ya iner; edge yoksa negatif.")
    print()


def geo_growth_check():
    print(line); print("2) GEOMETRİK BÜYÜME İDDİASI (rapor §7.2)")
    print(line)
    r, b, p, q = 0.05, 2.35, 0.90, 0.10
    G = (1 + r * b) ** p * (1 - r) ** q
    print(f"  G = (1+{r}·{b})^{p} · (1−{r})^{q} = {G:.4f}  (işlem başı geom. ort.)")
    n = 136
    print(f"  {n} işlemde: $100 · {G:.4f}^{n} = ${100*G**n:,.0f}")
    print(f"  -> Rapor 'gerçek $78K, geom. ort. sadece $37K' diyor ve aradaki")
    print(f"     farkı 'ORP kurtarma mekanizması' ile açıklıyor.")
    print()
    print("  HATA: Geometrik ortalama, bir stratejinin uzun-vade büyüme oranının")
    print("  ÜST SINIRIDIR (Kelly/ergodisite teoremi). Hiçbir 'kurtarma' (martingale)")
    print("  mekanizması beklenen geometrik büyümeyi AŞAMAZ; sadece varyansı ve")
    print("  iflas riskini artırır. '$37K teori < $78K gerçek' ifadesi, sonucun")
    print("  edge'den değil ölçüm hatasından geldiğinin bir işaretidir.")
    print()


def liquidation_check():
    print(line); print("3) 'LİKİDASYON İMKANSIZ' İDDİASI (rapor §7.4)")
    print(line)
    print("  Rapor: '5x kaldıraçta likidasyon için fiyat %20 ters gitmeli, SL ise")
    print("  ortalama %2 — yani likidasyon matematiksel olarak imkansız.'")
    print()
    print("  HATA: SL 'tetiklenir' ≠ SL 'o fiyattan dolar'. Flash-crash / gap /")
    print("  düşük likiditede fiyat SL'i ATLAR (slippage). %20'lik tek mumluk")
    print("  hareketler kriptoda nadir değildir (örn. çöküş günleri). Ayrıca")
    print("  'ortalama %2 SL' yanıltıcı; raporun kendi guard'ı SL'e %10'a kadar")
    print("  izin veriyor -> 5x'te %10 SL, %20 likidasyona sadece 2 kat uzakta.")
    print("  '0 likidasyon' ampirik kanıtı da look-ahead'li backtest'ten geliyor.")
    print()


def paroli_montecarlo():
    print(line); print("4) PAROLI / MONTE CARLO İDDİASI (rapor §5.3) — $916 MİLYAR")
    print(line)
    print("  Rapor, Paroli ile 400 işlemde medyan $411B 'kanıtlıyor'. Bunu kendi")
    print("  Monte Carlo'sunda p=%90 kazanma + pozitif R varsayarak üretiyor.")
    print("  Sorgu: edge GERÇEKÇİ olursa (p düşük), Paroli ne yapar?")
    print()
    rng = np.random.default_rng(7)
    R_win, R_loss = 2.35, -1.0
    for p in [0.90, 0.55, 0.50, 0.45]:
        finals = []
        ruined = 0
        for _ in range(2000):
            eq = 100.0; cw = 0
            for _t in range(400):
                risk = min(0.02 * (2 ** cw), 0.15)
                stake = eq * risk
                if rng.random() < p:       # WIN
                    eq += stake * R_win; cw += 1
                    if cw >= 3: cw = 0
                else:                      # LOSS
                    eq += stake * R_loss; cw = 0
                if eq < 1.0:
                    ruined += 1; eq = 0.0; break
            finals.append(eq)
        finals = np.array(finals)
        med = np.median(finals)
        print(f"  p=%{p*100:.0f}: medyan ${med:,.0f}  ortalama ${finals.mean():,.2e}  "
              f"iflas oranı %{ruined/2000*100:.1f}")
    print()
    print("  Yorum: Astronomik rakamlar SADECE p=%90 varsayımının ürünüdür.")
    print("  p gerçekçi (%50-55) olduğunda Paroli'nin beklendiği gibi medyanı")
    print("  düşer ve iflas riski patlar. $916B bir 'kanıt' değil, hatalı")
    print("  girdinin (şişirilmiş win-rate) üstel olarak büyütülmüş halidir.")
    print()


def orp_is_martingale():
    print(line); print("5) ORP SİSTEMİ ASLINDA NEDİR? (rapor §3.2)")
    print(line)
    print("  ORP: required_risk = max(equity·0.025, (hedef − equity)/1.5)")
    print("  Yani kayıptan sonra hedefin gerisine düşülünce RİSK ARTIRILIR.")
    print("  -> Bu bir MARTINGALE/hedef-takipli kurtarma sistemidir.")
    print("  Beklenen değeri negatif/sıfır olan bir oyunda martingale, iflas")
    print("  olasılığını artırır; pozitif edge'i olan oyunda ise Kelly'nin")
    print("  altında/üstünde sapma yaratıp geometrik büyümeyi DÜŞÜRÜR.")
    print("  '%15 ruin guard' iflası geciktirir ama edge yoksa engelleyemez.")
    print()


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  RAPORUN İÇ MATEMATİĞİNİN DENETİMİ")
    print("=" * 70 + "\n")
    kelly_check()
    geo_growth_check()
    liquidation_check()
    paroli_montecarlo()
    orp_is_martingale()
