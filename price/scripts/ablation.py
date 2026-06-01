"""Ablasyon testi — hangi bileşen IS↔OOS tutarlı katkı veriyor?

backtest.py'deki backtest() motorunu kullanır. Veri sembol başına BİR kez
çekilir (klines + HTF + funding) ve tüm konfiglerde bellekten tekrar kullanılır
→ Binance'i dövmez. Her konfig hem IS hem OOS sembol setinde ölçülür; edge
ancak HER İKİSİNDE de pozitifse "gerçek" sayılır.

Kullanım:
  python3 scripts/ablation.py            # canlı, varsayılan IS/OOS setleri
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
from pa import data as datamod                      # noqa: E402
import backtest as bt                                # noqa: E402

IS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT"]
OOS = ["LINK/USDT", "AVAX/USDT", "DOT/USDT", "LTC/USDT",
       "ATOM/USDT", "NEAR/USDT", "APT/USDT", "INJ/USDT"]
TF, HTF, LIMIT, K = "1h", "4h", 1000, 2
MAKER, TAKER, SLIP = 0.0002, 0.0005, 0.0002       # oransal (=%0.02/0.05/0.02)
LONDON = {7, 8, 9, 10, 11}

# Temel (full) konfig: kısmi kâr-al açık, HTF filtre açık, gerçekçi maliyet.
BASE = dict(part_frac=0.5, part_at=1.0, min_stop_pct=0.0,
            use_htf=True, use_funding=False, fund_thr=0.0001,
            pd_gate=False, hours=None, sides=None)

# Ablasyon konfigleri: (etiket, BASE üzerine farklar)
CONFIGS = [
    ("BASE (HTF+kısmi+maliyet)",         {}),
    ("− kısmi kâr-al",                    dict(part_frac=0.0)),
    ("− HTF filtresi",                    dict(use_htf=False)),
    ("+ min-stop %0.3",                   dict(min_stop_pct=0.3)),
    ("+ PD-gate (ICT)",                   dict(pd_gate=True)),
    ("+ funding-fade",                    dict(use_funding=True)),
    ("+ Londra saat (07-11)",            dict(hours=LONDON)),
    ("+ sadece SHORT",                    dict(sides={"SHORT"})),
    ("+ Londra + SHORT",                 dict(hours=LONDON, sides={"SHORT"})),
]


def load(symbols):
    """Sembol → (entry, htf, funding). Bir kez çek, cache'le."""
    cache = {}
    for s in symbols:
        try:
            entry = datamod.fetch_ohlcv(s, TF, LIMIT)
            htf = datamod.fetch_ohlcv(s, HTF, LIMIT)
            fund = bt.fetch_funding(s, 1000)
        except Exception as e:  # noqa: BLE001
            print(f"  [{s}] veri alınamadı: {e}", file=sys.stderr)
            continue
        if len(entry) >= bt.WARMUP + bt.HORIZON:
            cache[s] = (entry, htf, fund)
    return cache


def run_config(cache, cfg):
    c = dict(BASE)
    c.update(cfg)
    trades = []
    for entry, htf, fund in cache.values():
        tr, _ = bt.backtest(
            entry, htf if c["use_htf"] else None, HTF if c["use_htf"] else "",
            K, MAKER, TAKER, SLIP, c["part_frac"], c["part_at"],
            c["min_stop_pct"], fund if c["use_funding"] else None,
            c["fund_thr"], c["pd_gate"], c["hours"], c["sides"])
        trades += tr
    n, w, wr, _, gross, net, _ = bt._stats(trades)
    return n, wr, gross, net


def main():
    t0 = time.time()
    print("# Veri çekiliyor (sembol başına 1 kez)...", flush=True)
    is_cache = load(IS)
    oos_cache = load(OOS)
    print(f"# IS {len(is_cache)} sembol · OOS {len(oos_cache)} sembol · "
          f"{time.time() - t0:.0f}s\n", flush=True)

    hdr = f"{'KONFİG':<26} | {'IS n':>5} {'IS NET/işl':>11} | " \
          f"{'OOS n':>5} {'OOS NET/işl':>12} | KARAR"
    print(hdr)
    print("-" * len(hdr))
    for label, cfg in CONFIGS:
        isn, iswr, isg, isnet = run_config(is_cache, cfg)
        on, owr, og, onet = run_config(oos_cache, cfg)
        is_e = isnet / isn if isn else 0.0
        oos_e = onet / on if on else 0.0
        # "gerçek" = her iki sette de pozitif ve makul örneklem
        verdict = ("✓ TUTARLI" if (is_e > 0 and oos_e > 0 and isn >= 20 and on >= 20)
                   else "yarı (sadece IS)" if is_e > 0
                   else "✗")
        print(f"{label:<26} | {isn:>5} {is_e:>+10.3f}R | "
              f"{on:>5} {oos_e:>+11.3f}R | {verdict}", flush=True)


if __name__ == "__main__":
    main()
