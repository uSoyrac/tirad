# quantlab botları (Claude / quantlab araştırması) — combo / momentum / funding

Bu üç bot, izole `quantlab/` çok-ajanlı araştırma sisteminin dürüst, OOS-doğrulanmış
(look-ahead yok; komisyon + slippage + funding + likidasyon + kill-switch dahil)
kazananlarıdır. `quantlab` paketini kullanır, 20-coin evreninde (`uyg/src/mktdata` +
`funddata`) çalışır. Bu klasördeki `bot_kararli/dengeli/optimal` (diğer agent, XGBoost
kapısı + TP5/SL2.5) ayrı bir ailedir; bunlar onlardan FARKLI bir yaklaşımdır.

## Botlar
| Bot | Yaklaşım | OOS 2025-26 (dürüst) |
|---|---|---|
| **`bot_combo.py`** ★ | Trend Top-3 + Funding-pozisyonlama, ortogonal, inverse-vol (train-fit) | **Sharpe ~1.74** (WF-opt ~2.25), MaxDD −14% |
| `bot_xsec_momentum.py` | 20 coin arası en güçlü momentum Top-3 | Win %41.8, +$70/işlem, Sharpe 1.12 |
| `bot_funding.py` | Yüksek-funding short / düşük-funding long, market-nötr | Sharpe 1.31 (ortogonal) |

## Çalıştırma
```bash
quantlab/.venv/bin/python uyg/Botlar/bot_combo.py
```
Her bot dürüst OOS özeti + şu an tutulması gereken pozisyonları yazar.

## Önerim (en optimal)
**`bot_combo`** — bake-off'un risk-ayarlı galibi. İki ortogonal edge'in (korelasyon −0.06)
çeşitlendirmesi tek koldan hem daha yüksek Sharpe hem daha düşük drawdown verir VE random
alt-evren testinde trend-tek-başına'dan daha sağlamdır (medyan 0.48 vs 0.06).

## Dürüst sınırlar (her iki aile için de geçerli)
- **Paper-trading adayı, canlı sermaye DEĞİL.** İleriye-dönük doğrulama şart.
- **Survivorship bias:** evren bugünün hayatta kalanları (~%15-22/yıl şişirme tahmini) →
  işaret/dayanıklılığa güven, mutlak büyüklüğe değil. Gerçek dağıtımdan önce point-in-time evren.
- Quantlab framework'ünde bağımsız test ettiğimde: XGBoost kalite-kapısı OOS AUC ~0.52
  (yazı-tura) çıktı ve portföye gate olarak eklemek Sharpe'ı düşürdü; kaldıraçlı asimetrik
  "sniper" (TP10/SL2) negatif-EV + kill-switch'i patlattı. Bu yüzden benim ailem
  gate'siz portföy-seviyesi edge'lere (momentum dispersiyonu + funding ortogonalitesi)
  dayanır. Diğer ailenin TP5/SL2.5 + tek-pozisyon 1H kurulumu farklı bir konfigürasyon —
  kendi README'lerindeki "deflated Sharpe ~%31, paper-trade first" uyarıları yerinde.
