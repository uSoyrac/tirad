

# ════════════════════════════════════════════════════════════════════════════
# EK SEKME: /sinyal — MANUEL işlem listesi (bot-yasaklı firmalar için)
# signal_report.py'nin yazdığı paper/signal.json'u gösterir. (additive. Claude.)
# ════════════════════════════════════════════════════════════════════════════
@app.route("/sinyal")
@requires_auth
def sinyal_panel():
    import json
    import os
    import html as _h

    def esc(x):
        return _h.escape(str(x)) if x is not None else "—"

    path = os.path.join(PAPER_DIR, "signal.json") if "PAPER_DIR" in globals() else "/root/tirad/paper/signal.json"
    try:
        r = json.load(open(path))
    except Exception:
        r = None
    if not r:
        body = "<p class=muted>Henüz sinyal yok. <code>signal_report.py</code> cron'u ilk çalışınca görünür.</p>"
    else:
        def acol(a):
            return {"AÇ": "#3fb950", "TUT": "#8b949e", "KAPAT": "#f85149"}.get(a, "#e6edf3")
        rows = "".join(
            f"<tr><td style='color:{acol(p.get('action'))};font-weight:700'>{esc(p.get('action'))}</td>"
            f"<td style='color:{'#3fb950' if p.get('side')=='LONG' else '#f85149'};font-weight:600'>{esc(p.get('side'))}</td>"
            f"<td><b>{esc(p.get('coin'))}</b></td><td>{esc(p.get('entry'))}</td>"
            f"<td>{esc(p.get('stop'))} <span class=muted>(%{esc(p.get('stop_pct'))})</span></td>"
            f"<td>%{esc(p.get('weight_pct'))}</td><td class=muted>{esc(p.get('rationale'))}</td></tr>"
            for p in (r.get("positions") or []))
        closes = "".join(
            f"<tr><td style='color:#f85149;font-weight:700'>KAPAT</td><td>{esc(c.get('side'))}</td>"
            f"<td><b>{esc(c.get('coin'))}</b></td><td colspan=4 class=muted>sinyalden çıktı — pozisyonu kapat</td></tr>"
            for c in (r.get("closes") or []))
        body = f"""
<div class=badge>Rejim: {esc(r.get('regime'))} · {esc(r.get('n_pos'))} pozisyon · as-of {esc(r.get('asof'))}</div>
<p class=note>{esc(r.get('note'))}</p>
<table><tr><th>Aksiyon</th><th>Yön</th><th>Coin</th><th>Giriş≈</th><th>Stop-loss (zorunlu)</th><th>Ağırlık</th><th>Gerekçe</th></tr>
{rows}{closes}</table>
<p class=muted style="margin-top:12px">Son güncelleme: {esc(r.get('ts'))} · Bu liste MANUEL içindir —
firma platformunda elle gir, her pozisyona stop-loss koy, sinyalden çıkana (KAPAT) kadar tut.</p>
"""
    tpl = """<!doctype html><html lang=tr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>TIRAD — Manuel Sinyal</title>
<style>body{background:#0d1117;color:#e6edf3;font-family:system-ui,Arial;margin:0;padding:16px}
a{color:#58a6ff}h1{font-size:20px}table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:6px 9px;border-bottom:1px solid #21262d;text-align:left}th{color:#8b949e}
.muted{color:#8b949e}.sub{color:#8b949e;font-size:12px;margin-bottom:10px}
.badge{display:inline-block;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:6px 12px;margin:6px 0;font-weight:600}
.note{background:#161b22;padding:10px 12px;border-radius:8px;font-size:12px;color:#c9d1d9}</style></head><body>
<h1>📡 TIRAD — Manuel İşlem Sinyali</h1>
<div class=sub>Bot-yasaklı firmalar için elle uygulanacak liste · <a href="/">🏠</a> · <a href="/bybit">🟡 Bybit</a> · <a href="/saglik">🩺 Sağlık</a> · <a href="/arastirma">🔬 Re-Research</a></div>
__BODY__
</body></html>"""
    return tpl.replace("__BODY__", body)
