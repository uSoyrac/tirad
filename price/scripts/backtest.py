"""Backtest / kural doğrulama (stdlib) — teşhis sürümü.

Motorun ürettiği setup'ları geçmiş mumlarda yürütür ve GERÇEK isabet/R/R
dağılımını ölçer. "Bu kurallar gerçekten çalışıyor mu / nerede kaybediyor?"

Özellikler:
  - Look-ahead YOK: setup yalnızca candles[:i+1] ile kurulur.
  - HTF confluence filtresi (CLI'deki gibi): üst TF yönüne ters setup elenir.
    HTF yönü, o ana kadar KAPANMIŞ üst-TF mumlarından hesaplanır (gelecek yok).
  - Maliyet: komisyon + slippage (gidiş-dönüş), R cinsinden düşülür → NET sonuç.
  - Teşhis: MFE/MAE (lehe/aleyhe azami sapma, R) — kısmi kâr-al işe yarar mı?
  - Çok sembol; $ raporu (sabit-kesir risk).

Kullanım:
  python3 scripts/backtest.py --live --symbols BTC/USDT,ETH/USDT,SOL/USDT \\
          --tf 1h --htf 4h --limit 1000 --portfolio 1000 --risk-pct 1
  python3 scripts/backtest.py --csv data/sample_btc_1h.csv        # HTF'siz
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

sys.path.insert(0, ".")
from pa import data as datamod                 # noqa: E402
from pa.types import Bias, Candle, Side         # noqa: E402
from pa.setup import build_setup               # noqa: E402
from pa.analyze import htf_bias                 # noqa: E402

WARMUP = 60
HORIZON = 120
_TF_MS = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
          "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
          "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800}


def tf_ms(tf: str) -> int:
    if tf not in _TF_MS:
        raise ValueError(f"bilinmeyen TF: {tf}")
    return _TF_MS[tf] * 1000


@dataclass
class Trade:
    symbol: str
    side: Side
    rr: float
    gross_R: float          # +rr (hedef) | -1 (stop)
    net_R: float            # gross - maliyet
    mfe_R: float            # dolumdan sonra azami LEHE sapma (R)
    mae_R: float            # azami ALEYHE sapma (R)


def htf_bias_at(htf: Sequence[Candle], ts_ms: int, htfms: int, k: int) -> Bias:
    """ts_ms'den ÖNCE tamamen kapanmış üst-TF mumlarından yön (look-ahead yok)."""
    usable = [c for c in htf if c.ts + htfms <= ts_ms]
    if len(usable) < 4 * k + 5:
        return Bias.NEUTRAL
    return htf_bias(usable, k=k)


def _simulate(s, candles: Sequence[Candle], i: int, cost_R: float,
              part_frac: float = 0.0, part_at: float = 1.0) -> Optional[Trade]:
    """part_frac>0 ise: part_at R'de pozisyonun part_frac'ı kapatılır ve stop
    girişe (breakeven) çekilir; kalan hedefe kadar taşınır. (ihtiyatlı: bir
    barda hem stop hem lehe seviye varsa stop önce sayılır.)"""
    n = len(candles)
    is_long = s.side == Side.LONG
    risk = abs(s.entry - s.stop)
    if risk == 0:
        return None
    fill = None
    mfe = mae = 0.0
    part_done = False
    stop_lvl = s.stop
    realized = 0.0
    for j in range(i + 1, min(i + 1 + HORIZON, n)):
        c = candles[j]
        if fill is None:
            if c.low <= s.entry <= c.high:
                fill = j
            else:
                continue
        if is_long:
            mfe = max(mfe, (c.high - s.entry) / risk)
            mae = max(mae, (s.entry - c.low) / risk)
            hit_stop = c.low <= stop_lvl
            hit_part = c.high >= s.entry + part_at * risk
            hit_tgt = c.high >= s.target
        else:
            mfe = max(mfe, (s.entry - c.low) / risk)
            mae = max(mae, (c.high - s.entry) / risk)
            hit_stop = c.high >= stop_lvl
            hit_part = c.low <= s.entry - part_at * risk
            hit_tgt = c.low <= s.target

        if hit_stop:                        # ihtiyatlı: stop önce
            g = realized + (0.0 if part_done else -1.0)
            return Trade(s.symbol, s.side, s.rr, g, g - cost_R, mfe, mae)
        if part_frac > 0 and not part_done and hit_part:
            part_done = True
            stop_lvl = s.entry               # breakeven
            realized = part_frac * part_at
        if hit_tgt:
            g = realized + (1.0 - part_frac) * s.rr
            return Trade(s.symbol, s.side, s.rr, g, g - cost_R, mfe, mae)
    return None  # dolmadı / horizon içinde çözülmedi → istatistiğe alma


def backtest(entry: Sequence[Candle], htf: Optional[Sequence[Candle]],
             htf_tf: str, k: int, fee_pct: float, slip_pct: float,
             part_frac: float = 0.0, part_at: float = 1.0
             ) -> Tuple[List[Trade], int, int]:
    trades: List[Trade] = []
    skipped_htf = no_fill = 0
    htfms = tf_ms(htf_tf) if (htf and htf_tf) else 0
    roundtrip = 2.0 * (fee_pct + slip_pct) / 100.0   # oransal gidiş-dönüş
    n = len(entry)
    i = WARMUP
    while i < n - 1:
        s = build_setup(entry[: i + 1], k=k)
        if not s.valid:
            i += 1
            continue
        if htf:                                   # HTF confluence filtresi
            hb = htf_bias_at(htf, entry[i].ts, htfms, k)
            want = Bias.BULLISH if s.side == Side.LONG else Bias.BEARISH
            if hb != Bias.NEUTRAL and hb != want:
                skipped_htf += 1
                i += 1
                continue
        risk = abs(s.entry - s.stop)
        cost_R = (roundtrip * s.entry / risk) if risk else 0.0
        t = _simulate(s, entry, i, cost_R, part_frac, part_at)
        if t is None:
            no_fill += 1
            i += 1
            continue
        trades.append(t)
        # çözülme sonrası ilerle: kabaca dolum+1 yerine güvenli atla
        i += 1
    return trades, skipped_htf, no_fill


def _stats(trades: List[Trade]):
    n = len(trades)
    wins = [t for t in trades if t.gross_R > 0]
    gross = sum(t.gross_R for t in trades)
    net = sum(t.net_R for t in trades)
    wr = len(wins) / n * 100 if n else 0
    avg_rr = sum(t.rr for t in trades) / n if n else 0
    loser_mfe = [t.mfe_R for t in trades if t.gross_R < 0]
    avg_loser_mfe = sum(loser_mfe) / len(loser_mfe) if loser_mfe else 0
    return n, len(wins), wr, avg_rr, gross, net, avg_loser_mfe


def report(trades: List[Trade], skipped_htf: int, no_fill: int,
           portfolio: float, risk_pct: float) -> str:
    n, w, wr, avg_rr, gross, net, loser_mfe = _stats(trades)
    o = ["# Backtest (HTF filtresi + maliyet + teşhis)"]
    o.append(f"  İşlem (dolan&çözülen) : {n}   "
             f"[HTF eledi: {skipped_htf} · dolmadı/açık: {no_fill}]")
    if n == 0:
        o.append("  ⚠️ İstatistik için işlem yok.")
        return "\n".join(o)
    be = 1.0 / (1.0 + avg_rr) * 100.0
    per_R = portfolio * risk_pct / 100.0
    o.append(f"  İsabet                : {wr:.1f}%  ({w}K/{n - w}Z)  "
             f"(başabaş eşiği {be:.1f}%)")
    o.append(f"  Ortalama planlanan R/R: {avg_rr:.2f}")
    o.append(f"  BRÜT  beklenti / toplam: {gross / n:+.3f} R / {gross:+.2f} R")
    o.append(f"  NET   beklenti / toplam: {net / n:+.3f} R / {net:+.2f} R   "
             + ("EDGE VAR ✓" if net > 0 else "edge yok ✗"))
    o.append(f"  $  (1R={per_R:.2f}$, sabit risk): NET {net * per_R:+.2f}$ "
             f"({portfolio:.0f}$ portföy, %{risk_pct:g}/işlem)")
    o.append(f"  TEŞHİS · kaybedenlerin ort. MFE: {loser_mfe:.2f} R  → "
             + ("kısmi kâr-al/BE-stop CİDDİ fayda sağlar" if loser_mfe >= 1.0
                else "kaybedenler lehe pek gitmiyor; sorun GİRİŞ kalitesinde"))
    return "\n".join(o)


def _load(args, symbol: str):
    if args.live:
        entry = datamod.fetch_ohlcv(symbol, args.tf, args.limit, args.exchange)
        htf = (datamod.fetch_ohlcv(symbol, args.htf, args.limit, args.exchange)
               if args.htf else None)
    else:
        entry = datamod.load_csv(args.csv)
        htf = None
    return entry, htf


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="backtest")
    p.add_argument("--csv", default="data/sample_btc_1h.csv")
    p.add_argument("--symbols", default="BTC/USDT", help="virgülle ayrılmış")
    p.add_argument("--tf", default="1h")
    p.add_argument("--htf", default=None, help="HTF confluence filtresi (örn 4h)")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--exchange", default="binance")
    p.add_argument("--live", action="store_true")
    p.add_argument("--fee-pct", type=float, default=0.04, help="taker, taraf başına")
    p.add_argument("--slip-pct", type=float, default=0.02, help="kayma, taraf başına")
    p.add_argument("--portfolio", type=float, default=1000.0)
    p.add_argument("--risk-pct", type=float, default=1.0)
    p.add_argument("--partial-frac", type=float, default=0.0,
                   help="X R'de kapatılacak pozisyon oranı (0=kapalı, örn 0.5)")
    p.add_argument("--partial-at", type=float, default=1.0,
                   help="kısmi kâr-al seviyesi (R)")
    p.add_argument("-k", type=int, default=2)
    args = p.parse_args(argv)

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if not args.live:
        symbols = symbols[:1]   # CSV tek sembol

    all_trades: List[Trade] = []
    tot_skip = tot_nofill = 0
    part = (f"kısmi {args.partial_frac:g}@{args.partial_at:g}R+BE"
            if args.partial_frac > 0 else "kısmi yok")
    print(f"# TF={args.tf} HTF={args.htf or '—'} limit={args.limit} "
          f"fee={args.fee_pct}%×2 slip={args.slip_pct}%×2 · {part}\n")
    for sym in symbols:
        try:
            entry, htf = _load(args, sym)
        except Exception as e:  # noqa: BLE001
            print(f"  [{sym}] veri alınamadı: {e}", file=sys.stderr)
            continue
        if len(entry) < WARMUP + HORIZON:
            print(f"  [{sym}] yetersiz mum ({len(entry)})", file=sys.stderr)
            continue
        tr, sk, nf = backtest(entry, htf, args.htf or "", args.k,
                              args.fee_pct, args.slip_pct,
                              args.partial_frac, args.partial_at)
        all_trades += tr
        tot_skip += sk
        tot_nofill += nf
        n, w, wr, avg_rr, gross, net, _ = _stats(tr)
        print(f"  [{sym}] {len(entry)} mum → işlem {n}, isabet {wr:.0f}%, "
              f"NET {net:+.2f}R")

    print()
    print(report(all_trades, tot_skip, tot_nofill, args.portfolio, args.risk_pct))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
