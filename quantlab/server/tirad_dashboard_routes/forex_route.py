

# ════════════════════════════════════════════════════════════════════════════
# EK SEKME: /forex — BOT 2 FX carry manuel sinyali (FundingPips/forex venue'leri)
# fx_carry_signal.py'nin yazdığı paper/fx_signal.json'u gösterir. (additive. Claude.)
# ════════════════════════════════════════════════════════════════════════════
@app.route("/forex")
@requires_auth
def forex_panel():
    import json
    import os
    import html as _h

    def esc(x):
        return _h.escape(str(x)) if x is not None else "—"

    path = os.path.join(PAPER_DIR, "fx_signal.json") if "PAPER_DIR" in globals() else "/root/tirad/paper/fx_signal.json"
    try:
        r = json.load(open(path))
    except Exception:
        r = None
    if not r:
        body = "<p class=muted>Henüz FX sinyali yok. <code>fx_carry_signal.py</code> çalışınca görünür.</p>"
    else:
        rows = "".join(
            f"<tr><td style='color:{'#3fb950' if 'LONG' in p.get('dir','') else '#f85149'};font-weight:700'>{esc(p.get('dir'))}</td>"
            f"<td><b>{esc(p.get('pair'))}</b></td><td>{esc(p.get('action'))}</td>"
            f"<td>{p.get('carry_pct'):+.2f}%/yıl</td></tr>"
            for p in (r.get("positions") or []))
        body = f"""
<div class=badge>BOT 2 — FX Carry · {esc(r.get('year'))} · {esc(r.get('split'))}</div>
<p class=note>{esc(r.get('note'))}</p>
<table><tr><th>Yön</th><th>Parite</th><th>Emir</th><th>Carry (yıllık)</th></tr>{rows}</table>
<p class=muted style="margin-top:12px">Son güncelleme: {esc(r.get('ts'))} · MODEST faktör (~0.5 Sharpe,
9/12 yıl +) — prop-passer değil, yavaş-gelir/diversifikasyon. Her pozisyona stop-loss zorunlu.</p>
"""
    tpl = """<!doctype html><html lang=tr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>TIRAD — FX Carry (Bot 2)</title>
<style>body{background:#0d1117;color:#e6edf3;font-family:system-ui,Arial;margin:0;padding:16px}
a{color:#58a6ff}h1{font-size:20px}table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:6px 9px;border-bottom:1px solid #21262d;text-align:left}th{color:#8b949e}
.muted{color:#8b949e}.sub{color:#8b949e;font-size:12px;margin-bottom:10px}
.badge{display:inline-block;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:6px 12px;margin:6px 0;font-weight:600}
.note{background:#161b22;padding:10px 12px;border-radius:8px;font-size:12px;color:#c9d1d9}</style></head><body>
<h1>💱 TIRAD — Bot 2: FX Carry (forex/FundingPips, manuel)</h1>
<div class=sub>Tek gerçek FX faktörü (modest) · <a href="/">🏠</a> · <a href="/sinyal">📡 Crypto Sinyal</a> · <a href="/bybit">🟡 Bybit</a> · <a href="/arastirma">🔬</a></div>
__BODY__
</body></html>"""
    return tpl.replace("__BODY__", body)
