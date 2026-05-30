# Price Section

Kaldıraçlı kripto işlemlerinde **fiyat hareketi (price action / SMC-ICT)** odaklı
analiz için hazırlanmış bölüm. Amaç: minimum riskle maksimum hedef — sadece
asimetrik (düşük risk / yüksek hedef) fırsatları yakalamak. Çoğu zaman doğru
cevap "işlem yok"tur.

## İçindekiler

| Dosya | Açıklama |
|-------|----------|
| [`analyst-prompt.md`](analyst-prompt.md) | Analist persona / sistem prompt'u — temel felsefe, analitik çekirdek, risk & kaldıraç kuralları, çıktı formatı. |
| [`concepts.md`](concepts.md) | Price action kavram sözlüğü — BOS, CHoCH, likidite, FVG, OB, PD array ve klasik PA yapıları. |
| [`data-sources.md`](data-sources.md) | Değerlendirilecek güncel veri kaynakları (funding, OI, long/short, whale, liquidation map vb.). |
| [`workflow.md`](workflow.md) | Analiz akışı, zaman dilimi & confluence kuralları, risk/kaldıraç hesabı, çıktı şablonu. |

## Temel Felsefe (özet)

- Her setup en az **1:2 R/R**, tercihen **1:3+**. Bunu sağlamayan fikir üretilmez.
- Stop yapısaldır (invalidasyon/likidite ötesi), keyfi değil. "Yanılırsam hemen
  anlarım, haklıysam çok kazanırım" yapısı aranır.
- Kaldıraç kuralı: **stop_yüzdesi × kaldıraç < 90**.
- Belirsizken kesin konuşulmaz; veri yoksa uydurulmaz.
- Çizgi > sayı: önce yapı (trend, kanal, swing dizilimi) okunur.
