"""pa — Price Action analiz motoru (saf Python, bağımlılıksız çekirdek).

Deterministik, kural-tabanlı SMC/ICT yapı tespiti:
swing, BOS/CHoCH, likidite (sweep / equal H-L), FVG, order block,
premium/discount (PD array), setup zinciri, risk & kaldıraç.

Tasarım: çekirdek motor yalnızca stdlib kullanır ve list[Candle] üzerinde
çalışır. Veri kaynağı (CSV her zaman; ccxt/Binance opsiyonel, lazy import)
ayrı katmandır. LLM yorum katmanı bu motorun yapısal çıktısının üstüne biner.
"""

__version__ = "0.1.0"
