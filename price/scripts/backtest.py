"""Backtest / kural doğrulama (stdlib).

Motorun ürettiği setup'ları geçmiş mumlarda yürütür ve gerçek isabet/R/R
dağılımını ölçer. "Bu kurallar gerçekten çalışıyor mu?" sorusunu yanıtlar.

Yöntem (look-ahead YOK):
  - Her bar i için setup yalnızca candles[:i+1] ile kurulur (gelecek görülmez).
  - Geçerli bir setup çıkınca, SONRAKİ barlarda (i+1..i+HORIZON) simüle edilir:
      1) Fiyat giriş bölgesine [entry_low, entry_high] dönerse emir dolar.
      2) Dolduktan sonra önce stop mu hedef mi vurulur? (aynı bar → stop, ihtiyatlı)
  - Çözülen trade'den sonra arama çözülme barından devam eder (üst üste binme yok).

Tek-TF (build_setup) kullanır; CLI'nin HTF confluence filtresi bu basit
sürümde uygulanmaz (ayrı bir doğrulama). Çıktı: trade sayısı, isabet, ort R,
beklenen değer (R/işlem), toplam R.

Kullanım:
  python3 scripts/backtest.py                      # data/sample_btc_1h.csv
  python3 scripts/backtest.py --csv yol.csv
  python3 scripts/backtest.py --symbol BTC/USDT --tf 1h --limit 1000   # canlı
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Sequence

sys.path.insert(0, ".")
from pa import data as datamod          # noqa: E402
from pa.types import Candle, Side        # noqa: E402
from pa.setup import build_setup         # noqa: E402

WARMUP = 60        # setup kurmadan önce gereken minimum mum
HORIZON = 120      # bir trade'in çözülmesi için bakılan azami ileri bar


class Trade:
    __slots__ = ("side", "rr", "entry", "stop", "target",
                 "open_bar", "fill_bar", "res_bar", "outcome_R")

    def __init__(self, s, open_bar):
        self.side = s.side
        self.rr = s.rr
        self.entry = s.entry
        self.stop = s.stop
        self.target = s.target
        self.open_bar = open_bar
        self.fill_bar: Optional[int] = None
        self.res_bar: Optional[int] = None
        self.outcome_R: Optional[float] = None   # +rr (kazanç), -1 (kayıp), None (çözülmedi)


def _simulate(s, candles: Sequence[Candle], i: int) -> Trade:
    """build_setup çıktısı s'yi bar i'den sonra ileri simüle et."""
    t = Trade(s, i)
    n = len(candles)
    is_long = s.side == Side.LONG
    for j in range(i + 1, min(i + 1 + HORIZON, n)):
        c = candles[j]
        if t.fill_bar is None:
            # limit giriş fiyatına dokunuldu mu?
            if c.low <= s.entry <= c.high:
                t.fill_bar = j
            else:
                continue
        # dolu: stop/hedef kontrolü (dolum barı dahil)
        if is_long:
            hit_stop = c.low <= s.stop
            hit_tgt = c.high >= s.target
        else:
            hit_stop = c.high >= s.stop
            hit_tgt = c.low <= s.target
        if hit_stop:                       # aynı bar her ikisi de → ihtiyatlı: stop
            t.outcome_R = -1.0
            t.res_bar = j
            return t
        if hit_tgt:
            t.outcome_R = s.rr
            t.res_bar = j
            return t
    return t   # fill_bar None ise dolmadı; doluysa horizon içinde çözülmedi


def backtest(candles: Sequence[Candle], k: int = 2):
    trades: List[Trade] = []
    no_fill = 0
    i = WARMUP
    n = len(candles)
    while i < n - 1:
        s = build_setup(candles[: i + 1], k=k)
        if not s.valid:
            i += 1
            continue
        t = _simulate(s, candles, i)
        if t.fill_bar is None:
            no_fill += 1
            i += 1                          # dolmadı; bir bar ilerle
            continue
        trades.append(t)
        i = (t.res_bar or t.fill_bar) + 1   # çözülme sonrası devam (binme yok)
    return trades, no_fill


def report(trades: List[Trade], no_fill: int) -> str:
    resolved = [t for t in trades if t.outcome_R is not None]
    unresolved = len(trades) - len(resolved)
    wins = [t for t in resolved if t.outcome_R > 0]
    losses = [t for t in resolved if t.outcome_R <= 0]
    n = len(resolved)
    out = ["# Backtest sonucu (tek-TF, build_setup)"]
    out.append(f"  Dolan & çözülen işlem : {n}")
    out.append(f"  Dolmayan setup        : {no_fill}")
    out.append(f"  Horizon içinde açık   : {unresolved}")
    if n == 0:
        out.append("  ⚠️ Çözülen işlem yok — istatistik üretilemiyor.")
        return "\n".join(out)
    wr = len(wins) / n * 100.0
    total_R = sum(t.outcome_R for t in resolved)
    exp_R = total_R / n
    avg_win = sum(t.outcome_R for t in wins) / len(wins) if wins else 0.0
    avg_planned_rr = sum(t.rr for t in resolved) / n
    longs = [t for t in resolved if t.side == Side.LONG]
    shorts = [t for t in resolved if t.side == Side.SHORT]
    out.append(f"  İsabet (win rate)     : {wr:.1f}%  ({len(wins)}K / {len(losses)}Z)")
    out.append(f"  Ortalama planlanan R/R: {avg_planned_rr:.2f}")
    out.append(f"  Ortalama kazanç (R)   : +{avg_win:.2f}")
    out.append(f"  Beklenen değer (R/işl): {exp_R:+.3f}")
    out.append(f"  Toplam R              : {total_R:+.2f}")
    out.append(f"  Yön dağılımı          : {len(longs)} long / {len(shorts)} short")
    # başabaş isabet eşiği (R=ortalama planlanan): 1/(1+R)
    be = 1.0 / (1.0 + avg_planned_rr) * 100.0
    out.append(f"  Başabaş isabet eşiği  : {be:.1f}%  → "
               + ("EDGE VAR ✓" if wr > be else "edge yok ✗"))
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="backtest")
    p.add_argument("--csv", default="data/sample_btc_1h.csv")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--tf", default="1h")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--exchange", default="binance")
    p.add_argument("--live", action="store_true", help="CSV yerine canlı çek")
    p.add_argument("-k", type=int, default=2)
    args = p.parse_args(argv)

    if args.live:
        candles = datamod.fetch_ohlcv(args.symbol, args.tf, args.limit, args.exchange)
        src = f"{args.exchange} {args.symbol} {args.tf} (canlı, {len(candles)} mum)"
    else:
        candles = datamod.load_csv(args.csv)
        src = f"CSV {args.csv} ({len(candles)} mum)"

    if len(candles) < WARMUP + HORIZON:
        print(f"⚠️ Yetersiz mum ({len(candles)}); en az {WARMUP+HORIZON} gerekir.",
              file=sys.stderr)
        return 2

    trades, no_fill = backtest(candles, k=args.k)
    print(f"# Kaynak: {src}\n")
    print(report(trades, no_fill))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
