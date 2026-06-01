"""BÖLÜM 2 — canlı veri okuması (funding / OI / long-short).

Felsefe: erişilemeyen kaynağı UYDURMA. Her metrik 'available' bayrağı taşır;
çekilemezse note'a hata yazılır ve rapor onu açıkça eksik işaretler.

Bağımlılık: yalnızca stdlib (urllib). HTTP çağrısı `http_get` ile enjekte
edilebilir → ağsız test edilebilir. Varsayılan sağlayıcı Binance USDⓈ-M
Futures public endpoint'leridir (anahtarsız); ağ erişimi gereklidir.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# (url) -> ham gövde (str). Test/enjeksiyon için değiştirilebilir.
HttpGet = Callable[[str], str]

FAPI = "https://fapi.binance.com"


def _default_http_get(url: str, timeout: float = 8.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode()


def _to_symbol(symbol: str) -> str:
    """'BTC/USDT' -> 'BTCUSDT' (Binance futures formatı)."""
    return symbol.replace("/", "").replace("-", "").upper()


@dataclass
class Metric:
    name: str
    available: bool
    value: Optional[float] = None
    unit: str = ""
    note: str = ""           # erişilemezse hata; erişilirse kısa yorum

    def line(self) -> str:
        if not self.available:
            return f"  ⚠️ {self.name}: alınamadı ({self.note})"
        val = f"{self.value:g}{self.unit}" if self.value is not None else "?"
        extra = f" — {self.note}" if self.note else ""
        return f"  • {self.name}: {val}{extra}"


@dataclass
class DataReading:
    symbol: str
    metrics: List[Metric] = field(default_factory=list)

    @property
    def any_available(self) -> bool:
        return any(m.available for m in self.metrics)

    def crowded_side(self) -> Optional[str]:
        """Veriden kalabalık tarafı çıkar (kontra okuma için). Yetersizse None.

        - Pozitif funding + long/short>1 → kalabalık LONG (squeeze riski aşağı).
        - Negatif funding + long/short<1 → kalabalık SHORT (squeeze riski yukarı).
        Karışıksa None.
        """
        funding = next((m for m in self.metrics
                        if m.name == "Funding Rate" and m.available), None)
        ls = next((m for m in self.metrics
                   if m.name == "Long/Short Ratio" and m.available), None)
        votes = []
        if funding and funding.value is not None:
            votes.append("LONG" if funding.value > 0 else "SHORT")
        if ls and ls.value is not None:
            votes.append("LONG" if ls.value > 1 else "SHORT")
        if votes and all(v == votes[0] for v in votes):
            return votes[0]
        return None

    def render(self) -> str:
        if not self.metrics:
            return "  ⚠️ Hiçbir veri kaynağı denenmedi."
        lines = [m.line() for m in self.metrics]
        crowd = self.crowded_side()
        if crowd:
            lines.append(f"  ↳ Kalabalık taraf: {crowd} "
                         f"(kontra senaryoya dikkat).")
        elif self.any_available:
            lines.append("  ↳ Kalabalık taraf belirsiz (veri karışık).")
        return "\n".join(lines)


# --- bireysel fetcher'lar (hata fırlatır; collect yakalar) ---

def fetch_funding(symbol: str, http_get: HttpGet) -> Metric:
    url = f"{FAPI}/fapi/v1/premiumIndex?symbol={_to_symbol(symbol)}"
    data = json.loads(http_get(url))
    rate = float(data["lastFundingRate"]) * 100.0  # % olarak
    side = "longlar öder (kalabalık long)" if rate > 0 else \
           "shortlar öder (kalabalık short)" if rate < 0 else "nötr"
    return Metric("Funding Rate", True, value=round(rate, 4), unit="%", note=side)


def fetch_open_interest(symbol: str, http_get: HttpGet) -> Metric:
    url = f"{FAPI}/fapi/v1/openInterest?symbol={_to_symbol(symbol)}"
    data = json.loads(http_get(url))
    oi = float(data["openInterest"])
    return Metric("Open Interest", True, value=round(oi, 2), unit=" kontrat",
                  note="pozisyon yoğunluğu (trend için zaman serisi gerekir)")


def fetch_long_short(symbol: str, http_get: HttpGet,
                     period: str = "5m") -> Metric:
    url = (f"{FAPI}/futures/data/globalLongShortAccountRatio"
           f"?symbol={_to_symbol(symbol)}&period={period}&limit=1")
    data = json.loads(http_get(url))
    if not data:
        raise ValueError("boş long/short yanıtı")
    ratio = float(data[-1]["longShortRatio"])
    note = "long ağırlıklı" if ratio > 1 else "short ağırlıklı" if ratio < 1 else "dengeli"
    return Metric("Long/Short Ratio", True, value=round(ratio, 3), note=note)


_FETCHERS: Dict[str, Callable] = {
    "funding": fetch_funding,
    "oi": fetch_open_interest,
    "ls": fetch_long_short,
}


def collect(symbol: str = "BTC/USDT",
            http_get: Optional[HttpGet] = None) -> DataReading:
    """Tüm metrikleri dener; her birini ayrı ayrı yakalar. Bir kaynak
    çökerse diğerleri etkilenmez ve o kaynak 'alınamadı' işaretlenir."""
    get = http_get or _default_http_get
    reading = DataReading(symbol=symbol)
    names = {"funding": "Funding Rate", "oi": "Open Interest",
             "ls": "Long/Short Ratio"}
    for key, fn in _FETCHERS.items():
        try:
            reading.metrics.append(fn(symbol, get))
        except Exception as e:  # noqa: BLE001 — kaynak başarısızsa işaretle
            reading.metrics.append(
                Metric(names[key], False, note=f"{type(e).__name__}: {str(e)[:60]}"))
    return reading
