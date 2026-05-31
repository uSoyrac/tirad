"""Backtest / kural doğrulama (stdlib) — teşhis + gerçekçi maliyet.

Look-ahead YOK. Setup yalnızca candles[:i+1] ile kurulur.

Özellikler:
  - HTF confluence filtresi (CLI'deki gibi; üst-TF yalnızca KAPANMIŞ mumlardan).
  - Gerçekçi maliyet: giriş + hedef = MAKER (limit), stop = TAKER + slippage
    (market). Notional ağırlıklı, R cinsinden düşülür → NET sonuç.
  - Kısmi kâr-al + breakeven stop (--partial-frac).
  - --min-stop-pct: fee'nin ezdiği aşırı dar stoplu setup'ları ele.
  - Teşhis: MFE/MAE. Çok sembol; $ raporu.
  - Option 2: funding filtresi (--funding-fade) — geçmiş funding ile kalabalığı
    fade et (LONG yalnız funding<eşik, SHORT yalnız funding>+eşik).

Kullanım:
  python3 scripts/backtest.py --live --symbols BTC/USDT,ETH/USDT,SOL/USDT \\
    --tf 1h --htf 4h --limit 1000 --partial-frac 0.5 --min-stop-pct 0.6
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

sys.path.insert(0, ".")
from pa import data as datamod                 # noqa: E402
from pa.types import Bias, Candle, Side         # noqa: E402
from pa.setup import build_setup               # noqa: E402
from pa.analyze import htf_bias                 # noqa: E402

WARMUP = 60
HORIZON = 120
FAPI = "https://fapi.binance.com"
_TF_S = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
         "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
         "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800}


def tf_ms(tf: str) -> int:
    if tf not in _TF_S:
        raise ValueError(f"bilinmeyen TF: {tf}")
    return _TF_S[tf] * 1000


@dataclass
class Trade:
    symbol: str
    side: Side
    rr: float
    gross_R: float
    net_R: float
    mfe_R: float
    mae_R: float


def htf_bias_at(htf: Sequence[Candle], ts_ms: int, htfms: int, k: int) -> Bias:
    usable = [c for c in htf if c.ts + htfms <= ts_ms]
    if len(usable) < 4 * k + 5:
        return Bias.NEUTRAL
    return htf_bias(usable, k=k)


def fetch_funding(symbol: str, limit: int = 1000) -> List[Tuple[int, float]]:
    """(fundingTime_ms, rate) listesi (artan). Erişim yoksa boş döner."""
    sym = symbol.replace("/", "").replace("-", "").upper()
    url = f"{FAPI}/fapi/v1/fundingRate?symbol={sym}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode())
    return [(int(d["fundingTime"]), float(d["fundingRate"])) for d in data]


def funding_at(series: List[Tuple[int, float]], ts_ms: int) -> Optional[float]:
    """ts_ms'den önceki son funding oranı (look-ahead yok)."""
    val = None
    for ft, rate in series:
        if ft <= ts_ms:
            val = rate
        else:
            break
    return val


def _simulate(s, candles: Sequence[Candle], i: int,
              maker: float, taker: float, slip: float,
              part_frac: float, part_at: float) -> Optional[Trade]:
    n = len(candles)
    is_long = s.side == Side.LONG
    risk = abs(s.entry - s.stop)
    if risk == 0:
        return None
    unit = s.entry / risk                  # fee(oransal) → R çevrim katsayısı
    entry_cost = maker * unit              # giriş limit = maker (tam notional)
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

        if hit_stop:                        # ihtiyatlı: stop önce. market = taker+slip
            g = realized + (0.0 if part_done else -1.0)
            rem = (1.0 - part_frac) if part_done else 1.0
            cost = entry_cost + (maker * unit * part_frac if part_done else 0.0) \
                + (taker + slip) * unit * rem
            return Trade(s.symbol, s.side, s.rr, g, g - cost, mfe, mae)
        if part_frac > 0 and not part_done and hit_part:
            part_done = True
            stop_lvl = s.entry
            realized = part_frac * part_at
        if hit_tgt:                         # hedef limit = maker (tam çıkış)
            g = realized + (1.0 - part_frac) * s.rr
            cost = entry_cost + maker * unit
            return Trade(s.symbol, s.side, s.rr, g, g - cost, mfe, mae)
    return None


def backtest(entry: Sequence[Candle], htf: Optional[Sequence[Candle]],
             htf_tf: str, k: int, maker: float, taker: float, slip: float,
             part_frac: float, part_at: float, min_stop_pct: float,
             funding: Optional[List[Tuple[int, float]]], fund_thr: float):
    trades: List[Trade] = []
    skip_htf = skip_stop = skip_fund = no_fill = 0
    htfms = tf_ms(htf_tf) if (htf and htf_tf) else 0
    n = len(entry)
    i = WARMUP
    while i < n - 1:
        s = build_setup(entry[: i + 1], k=k)
        if not s.valid:
            i += 1
            continue
        if min_stop_pct > 0 and s.stop_pct < min_stop_pct:
            skip_stop += 1
            i += 1
            continue
        if htf:
            hb = htf_bias_at(htf, entry[i].ts, htfms, k)
            want = Bias.BULLISH if s.side == Side.LONG else Bias.BEARISH
            if hb != Bias.NEUTRAL and hb != want:
                skip_htf += 1
                i += 1
                continue
        if funding is not None:                       # Option 2: kalabalığı fade
            fr = funding_at(funding, entry[i].ts)
            if fr is not None:
                # LONG yalnız funding düşükse (shortlar kalabalık), SHORT tersi
                if s.side == Side.LONG and fr > fund_thr:
                    skip_fund += 1; i += 1; continue
                if s.side == Side.SHORT and fr < -fund_thr:
                    skip_fund += 1; i += 1; continue
        t = _simulate(s, entry, i, maker, taker, slip, part_frac, part_at)
        if t is None:
            no_fill += 1
            i += 1
            continue
        trades.append(t)
        i += 1
    return trades, dict(htf=skip_htf, stop=skip_stop, fund=skip_fund, nofill=no_fill)


def _stats(trades: List[Trade]):
    n = len(trades)
    wins = [t for t in trades if t.gross_R > 0]
    gross = sum(t.gross_R for t in trades)
    net = sum(t.net_R for t in trades)
    wr = len(wins) / n * 100 if n else 0
    avg_rr = sum(t.rr for t in trades) / n if n else 0
    loser_mfe = [t.mfe_R for t in trades if t.gross_R < 0]
    aml = sum(loser_mfe) / len(loser_mfe) if loser_mfe else 0
    return n, len(wins), wr, avg_rr, gross, net, aml


def report(trades, sk, portfolio, risk_pct) -> str:
    n, w, wr, avg_rr, gross, net, aml = _stats(trades)
    o = ["# TOPLAM"]
    o.append(f"  İşlem: {n}   [ele → HTF {sk['htf']} · dar-stop {sk['stop']} · "
             f"funding {sk['fund']} · dolmadı {sk['nofill']}]")
    if n == 0:
        o.append("  ⚠️ İşlem yok.")
        return "\n".join(o)
    per_R = portfolio * risk_pct / 100.0
    o.append(f"  İsabet: {wr:.1f}%  ({w}K/{n - w}Z)")
    o.append(f"  BRÜT beklenti/toplam: {gross / n:+.3f} R / {gross:+.2f} R")
    o.append(f"  NET  beklenti/toplam: {net / n:+.3f} R / {net:+.2f} R   "
             + ("EDGE VAR ✓" if net > 0 else "edge yok ✗"))
    o.append(f"  $ NET (1R={per_R:.0f}$): {net * per_R:+.2f}$")
    o.append(f"  teşhis · kaybeden MFE: {aml:.2f} R")
    return "\n".join(o)


def _load(args, symbol):
    if args.live:
        entry = datamod.fetch_ohlcv(symbol, args.tf, args.limit, args.exchange)
        htf = (datamod.fetch_ohlcv(symbol, args.htf, args.limit, args.exchange)
               if args.htf else None)
    else:
        entry, htf = datamod.load_csv(args.csv), None
    fund = None
    if args.funding_fade and args.live:
        try:
            fund = fetch_funding(symbol, 1000)
        except Exception as e:  # noqa: BLE001
            print(f"  [{symbol}] funding alınamadı: {e}", file=sys.stderr)
    return entry, htf, fund


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="backtest")
    p.add_argument("--csv", default="data/sample_btc_1h.csv")
    p.add_argument("--symbols", default="BTC/USDT")
    p.add_argument("--tf", default="1h")
    p.add_argument("--htf", default=None)
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--exchange", default="binance")
    p.add_argument("--live", action="store_true")
    p.add_argument("--maker-pct", type=float, default=0.02)
    p.add_argument("--taker-pct", type=float, default=0.05)
    p.add_argument("--slip-pct", type=float, default=0.02)
    p.add_argument("--partial-frac", type=float, default=0.0)
    p.add_argument("--partial-at", type=float, default=1.0)
    p.add_argument("--min-stop-pct", type=float, default=0.0)
    p.add_argument("--funding-fade", action="store_true")
    p.add_argument("--fund-thr", type=float, default=0.0001,
                   help="funding eşiği (oran, örn 0.0001 = %%0.01)")
    p.add_argument("--portfolio", type=float, default=1000.0)
    p.add_argument("--risk-pct", type=float, default=1.0)
    p.add_argument("-k", type=int, default=2)
    args = p.parse_args(argv)

    maker, taker, slip = args.maker_pct / 100, args.taker_pct / 100, args.slip_pct / 100
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if not args.live:
        symbols = symbols[:1]

    allt: List[Trade] = []
    agg = dict(htf=0, stop=0, fund=0, nofill=0)
    print(f"# tf={args.tf} htf={args.htf or '—'} limit={args.limit} "
          f"maker={args.maker_pct}% taker={args.taker_pct}% slip={args.slip_pct}% "
          f"| kısmi={args.partial_frac:g}@{args.partial_at:g}R "
          f"min_stop={args.min_stop_pct:g}% funding_fade={args.funding_fade}\n")
    for sym in symbols:
        try:
            entry, htf, fund = _load(args, sym)
        except Exception as e:  # noqa: BLE001
            print(f"  [{sym}] veri alınamadı: {e}", file=sys.stderr)
            continue
        if len(entry) < WARMUP + HORIZON:
            print(f"  [{sym}] yetersiz mum ({len(entry)})", file=sys.stderr)
            continue
        tr, sk = backtest(entry, htf, args.htf or "", args.k, maker, taker, slip,
                          args.partial_frac, args.partial_at, args.min_stop_pct,
                          fund if args.funding_fade else None, args.fund_thr)
        allt += tr
        for kk in agg:
            agg[kk] += sk[kk]
        n, w, wr, _, _, net, _ = _stats(tr)
        print(f"  [{sym}] {len(entry)} mum → işlem {n}, isabet {wr:.0f}%, "
              f"NET {net:+.2f}R")

    print()
    print(report(allt, agg, args.portfolio, args.risk_pct))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
