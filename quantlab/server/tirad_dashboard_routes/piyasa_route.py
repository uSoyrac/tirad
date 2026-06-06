

# ════════════════════════════════════════════════════════════════════════════
# EK SEKME: /piyasa — geçmiş piyasa datası (fiyat + değişim + SVG sparkline)
# (additive; kütüphane gerektirmez. Eklenme: Claude.)
# ════════════════════════════════════════════════════════════════════════════
@app.route("/piyasa")
@requires_auth
def piyasa():
    import os
    import html as _h
    import pandas as pd

    COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LTC", "ATOM", "DOT",
             "LINK", "DOGE", "ETC", "FIL", "INJ", "NEAR", "UNI", "APT", "ARB", "OP"]
    PQ = "/root/tirad/quantlab/data_cache"
    CSV = "/root/tirad/uyg/src/mktdata"

    def spark(vals, w=140, h=30):
        if len(vals) < 2:
            return ""
        lo, hi = min(vals), max(vals)
        rng = (hi - lo) or 1.0
        pts = " ".join(f"{i/(len(vals)-1)*w:.1f},{h-(v-lo)/rng*h:.1f}" for i, v in enumerate(vals))
        col = "#3fb950" if vals[-1] >= vals[0] else "#f85149"
        return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
                f'<polyline fill="none" stroke="{col}" stroke-width="1.5" points="{pts}"/></svg>')

    rows = []
    for c in COINS:
        df = None
        try:
            pqf = os.path.join(PQ, f"{c}_USDT_4h.parquet")
            csf = os.path.join(CSV, f"{c}_USDT_4h.csv")
            if os.path.exists(pqf):
                df = pd.read_parquet(pqf)
            elif os.path.exists(csf):
                df = pd.read_csv(csf)
        except Exception:
            df = None
        if df is None or "close" not in df.columns or len(df) < 10:
            continue
        close = df["close"].astype(float).to_numpy()
        last = float(close[-1])

        def chg(n):
            return (last / float(close[-1 - n]) - 1.0) * 100.0 if len(close) > n else 0.0

        asof = str(df["ts"].iloc[-1]) if "ts" in df.columns else str(df.index[-1])
        rows.append({"c": c, "last": last, "h4": chg(1), "d1": chg(6), "w1": chg(42),
                     "spark": spark(close[-90:].tolist()), "asof": asof})

    rows.sort(key=lambda r: r["w1"], reverse=True)

    def cell(v):
        col = "#3fb950" if v >= 0 else "#f85149"
        return f'<td style="color:{col}">{v:+.2f}%</td>'

    tr = []
    for r in rows:
        lp = f"{r['last']:,.4f}" if r["last"] < 10 else f"{r['last']:,.2f}"
        tr.append(f"<tr><td><b>{_h.escape(r['c'])}</b></td><td>${lp}</td>"
                  f"{cell(r['h4'])}{cell(r['d1'])}{cell(r['w1'])}"
                  f"<td>{r['spark']}</td><td class=muted>{_h.escape(r['asof'])}</td></tr>")
    BODY = "".join(tr) or "<tr><td colspan=7 class=muted>Veri bulunamadı (cache yok).</td></tr>"

    tpl = """<!doctype html><html lang=tr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>TIRAD — Piyasa</title>
<style>body{background:#0d1117;color:#e6edf3;font-family:system-ui,Arial;margin:0;padding:16px}
a{color:#58a6ff}h1{font-size:20px}table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:6px 9px;border-bottom:1px solid #21262d;text-align:left}th{color:#8b949e}
.muted{color:#8b949e;font-size:11px}.sub{color:#8b949e;font-size:12px;margin-bottom:10px}</style></head><body>
<h1>📈 TIRAD — Piyasa Datası (4h)</h1>
<div class=sub>Cache'ten · 7-günlük değişime göre sıralı · <a href="/">🏠 Tüm Botlar</a> · <a href="/rapor">📊 Rapor</a></div>
<table><tr><th>Coin</th><th>Son Fiyat</th><th>4h</th><th>24h</th><th>7g</th><th>Grafik (~15g)</th><th>as-of</th></tr>__BODY__</table>
</body></html>"""
    return tpl.replace("__BODY__", BODY)
