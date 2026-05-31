"""Çoklu sembol tarayıcı — VDS'de periyodik çalışmak için.

Bir sembol listesini verilen zaman dilimlerinde tarar, her biri için
analyze() çalıştırır ve SADECE geçerli setup'ları döndürür. Felsefe gereği
çoğu tarama "işlem yok" ile sonuçlanır; bu normaldir.

Ağ dayanıklılığı: bir sembolün verisi çekilemezse o sembol atlanır ve hata
kaydedilir; diğer semboller etkilenmez. Veri kaynağı (OHLCV fetcher ve
market.collect) enjekte edilebilir → ağsız test edilebilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

from .types import Candle
from .analyze import analyze, AnalysisResult
from . import data as datamod

# (symbol, timeframe, limit) -> list[Candle]
OhlcvFetcher = Callable[[str, str, int], List[Candle]]


@dataclass
class ScanItem:
    symbol: str
    result: Optional[AnalysisResult] = None
    error: Optional[str] = None  # veri çekilemediyse neden

    @property
    def valid(self) -> bool:
        return (self.error is None and self.result is not None
                and self.result.setup.valid)


@dataclass
class ScanReport:
    items: List[ScanItem] = field(default_factory=list)

    @property
    def valid_setups(self) -> List[ScanItem]:
        return [i for i in self.items if i.valid]

    @property
    def errors(self) -> List[ScanItem]:
        return [i for i in self.items if i.error is not None]


def _default_fetcher(symbol: str, timeframe: str, limit: int) -> List[Candle]:
    return datamod.fetch_ohlcv(symbol, timeframe, limit)


def scan(
    symbols: Sequence[str],
    *,
    entry_tf: str = "1h",
    htf: Optional[str] = "4h",
    limit: int = 300,
    k: int = 2,
    fetcher: Optional[OhlcvFetcher] = None,
) -> ScanReport:
    """symbols listesini tara. htf=None ise üst-TF filtresi uygulanmaz."""
    get = fetcher or _default_fetcher
    report = ScanReport()

    for symbol in symbols:
        try:
            entry = get(symbol, entry_tf, limit)
            htf_candles = get(symbol, htf, limit) if htf else None
        except Exception as e:  # noqa: BLE001 — veri yoksa sembolü atla, işaretle
            report.items.append(
                ScanItem(symbol=symbol, error=f"{type(e).__name__}: {str(e)[:80]}"))
            continue

        result = analyze(entry, htf_candles, entry_tf=entry_tf,
                         htf_tf=htf or "", symbol=symbol, k=k)
        report.items.append(ScanItem(symbol=symbol, result=result))

    return report
