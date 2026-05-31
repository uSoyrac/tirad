"""Sentetik örnek OHLCV CSV üretir (ağ bağımsız demo verisi).

Elle tasarlanmış, tam bir bullish ICT zinciri içerir:
  yukarıda eşit highs (BSL hedef) → SSL likidite havuzu → SSL sweep →
  yukarı displacement (BOS) → OB'ye geri çekiliş.
Motorun "geçerli setup" üreten mutlu yolunu deterministik olarak test eder.
"""

from __future__ import annotations

import csv
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "data", "sample_btc_1h.csv")

# (open, high, low, close)
ROWS = [
    (100, 101, 99, 100),
    (100, 102, 99, 101),
    (101, 142, 100, 140),   # 2  HIGH 142
    (140, 141, 128, 129),
    (129, 131, 127, 130),
    (130, 142, 129, 140),   # 5  HIGH 142 (eşit) -> BSL hedef havuzu 142
    (140, 141, 126, 127),
    (127, 129, 116, 117),
    (117, 119, 100, 101),   # 8  LOW 100
    (101, 108, 99.5, 107),
    (107, 112, 106, 111),
    (111, 113, 110, 112),
    (112, 114, 100, 102),   # 12 LOW 100 (eşit) -> SSL havuzu 100
    (102, 106, 101, 105),
    (105, 110, 104, 109),
    (109, 111, 108, 110),
    (110, 111, 93, 103),    # 16 SSL sweep @100 (fitil 93, kapanış 103)
    (103, 104, 100, 101),   # 17 son düşüş mumu = bullish OB
    (101, 118, 101, 117),   # 18 agresif yükseliş -> BOS
    (117, 124, 116, 123),
    (123, 126, 122, 125),
    (125, 127, 124, 126),
    (126, 127, 110, 111),   # 22 OB bölgesine geri çekiliş
    (111, 116, 109, 115),
]


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for i, (o, h, l, c) in enumerate(ROWS):
            w.writerow([i * 3600_000, o, h, l, c, 1.0])
    print(f"yazıldı: {len(ROWS)} mum -> {OUT}")


if __name__ == "__main__":
    main()
