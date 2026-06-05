

# ════════════════════════════════════════════════════════════════════════════
# EK SEKME: /bybit — Bybit TESTNET canlı hesap izleme (fon durumu, pozisyon, işlem, PnL)
# bybit_status.py'nin yazdığı paper/bybit_status.json'u gösterir. (additive. Claude.)
# ════════════════════════════════════════════════════════════════════════════
@app.route("/bybit")
@requires_auth
def bybit_panel():
    import json
    import os
    import html as _h

    def esc(x):
        return _h.escape(str(x)) if x is not None else "—"

    path = os.path.join(PAPER_DIR, "bybit_status.json") if "PAPER_DIR" in globals() else "/root/tirad/paper/bybit_status.json"
    try:
        r = json.load(open(path))
    except Exception:
        r = None

    if not r:
        body = "<p class=muted>Henüz veri yok. <code>bybit_status.py</code> cron'u ilk çalışınca görünür.</p>"
    elif not r.get("ok"):
        body = f"<p class=err>Bağlantı hatası: {esc(r.get('error'))}</p><p class=muted>as-of {esc(r.get('ts'))}</p>"
    else:
        eq = r.get("equity", 0)
        pnl = r.get("pnl_pct", 0)
        pcol = "#3fb950" if pnl >= 0 else "#f85149"
        funded = r.get("funded")
        fund_badge = ("🟢 FUNDED" if funded else "🧪 TESTNET — forward doğrulama (gerçek sermaye YOK)")
        # DD limitlerine mesafe çubukları
        dd_d, dd_t = r.get("daily_dd_pct", 0), r.get("total_dd_pct", 0)
        # spark (NAV)
        curve = [p.get("v") for p in (r.get("nav_curve") or []) if isinstance(p, dict)]
        spark = ""
        if len(curve) >= 2:
            lo, hi = min(curve), max(curve)
            rng = (hi - lo) or 1.0
            w, h = 320, 60
            pts = " ".join(f"{i/(len(curve)-1)*w:.1f},{h-(v-lo)/rng*h:.1f}" for i, v in enumerate(curve))
            col = "#3fb950" if curve[-1] >= curve[0] else "#f85149"
            spark = f'<svg width="{w}" height="{h}"><polyline fill="none" stroke="{col}" stroke-width="1.5" points="{pts}"/></svg>'

        pos_rows = "".join(
            f"<tr><td><b>{esc(p.get('sym'))}</b></td><td>{esc(p.get('side'))}</td>"
            f"<td>${esc(p.get('notional'))}</td><td>{esc(p.get('entry'))}</td>"
            f"<td style='color:{'#3fb950' if (p.get('upnl') or 0)>=0 else '#f85149'}'>${esc(p.get('upnl'))}</td></tr>"
            for p in (r.get("positions") or [])) or "<tr><td colspan=5 class=muted>Açık pozisyon yok</td></tr>"
        tr_rows = "".join(
            f"<tr><td>{esc(t.get('ts'))}</td><td><b>{esc(t.get('sym'))}</b></td><td>{esc(t.get('side'))}</td>"
            f"<td style='color:{'#3fb950' if (t.get('pnl') or 0)>=0 else '#f85149'}'>${esc(t.get('pnl'))}</td></tr>"
            for t in (r.get("recent_trades") or [])) or "<tr><td colspan=4 class=muted>Henüz kapanan işlem yok</td></tr>"

        body = f"""
<div class=badge>{fund_badge}</div>
<div class=grid>
  <div class=card><div class=lbl>Hedef Fon</div><div class=big>{esc(r.get('firm'))}</div></div>
  <div class=card><div class=lbl>Hesap Equity</div><div class=big>${esc(eq)} <span class=muted>USDT</span></div></div>
  <div class=card><div class=lbl>Toplam PnL</div><div class=big style="color:{pcol}">{pnl:+.2f}%</div>
       <div class=muted>başlangıç ${esc(r.get('start_eq'))}</div></div>
  <div class=card><div class=lbl>Açık pozisyon</div><div class=big>{esc(r.get('n_open'))}</div></div>
</div>
<div class=grid>
  <div class=card><div class=lbl>Günlük DD (limit {esc(r['limits']['daily'])}%)</div>
       <div class=big>{dd_d:+.2f}%</div><div class=muted>limite pay: {esc(r.get('daily_room'))} puan</div></div>
  <div class=card><div class=lbl>Toplam DD / trailing (limit {esc(r['limits']['total'])}%)</div>
       <div class=big>{dd_t:+.2f}%</div><div class=muted>limite pay: {esc(r.get('total_room'))} puan</div></div>
  <div class=card><div class=lbl>NAV (testnet)</div>{spark}</div>
</div>
<h3>Açık Pozisyonlar</h3>
<table><tr><th>Coin</th><th>Yön</th><th>Notional</th><th>Giriş</th><th>Anlık PnL</th></tr>{pos_rows}</table>
<h3>Son Kapanan İşlemler</h3>
<table><tr><th>Zaman</th><th>Coin</th><th>Yön</th><th>Realized PnL</th></tr>{tr_rows}</table>
<p class=muted style="margin-top:14px">as-of {esc(r.get('ts'))} · {esc(r.get('mode'))} ·
DD limitleri: günlük {esc(r['limits']['daily'])}% / toplam {esc(r['limits']['total'])}% (HyroTrader 2-step).
Fon durumu: {'FUNDED' if funded else 'henüz fon alınmadı — testnet doğrulama aşaması'}.</p>
"""

    tpl = """<!doctype html><html lang=tr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>TIRAD — Bybit Testnet</title>
<style>body{background:#0d1117;color:#e6edf3;font-family:system-ui,Arial;margin:0;padding:16px}
a{color:#58a6ff}h1{font-size:20px}h3{margin-top:20px}table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:6px 9px;border-bottom:1px solid #21262d;text-align:left}th{color:#8b949e}
.muted{color:#8b949e;font-size:12px}.err{color:#f85149}.sub{color:#8b949e;font-size:12px;margin-bottom:10px}
.badge{display:inline-block;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:6px 12px;margin:6px 0;font-weight:600}
.grid{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0}
.card{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:12px 14px;min-width:170px}
.lbl{color:#8b949e;font-size:12px}.big{font-size:20px;font-weight:700;margin-top:4px}</style></head><body>
<h1>🟡 TIRAD — Bybit Testnet (canlı hesap)</h1>
<div class=sub>Fon-alma denemesi · canlı izleme · <a href="/">🏠</a> · <a href="/rapor">📊 Rapor</a> · <a href="/saglik">🩺 Sağlık</a> · <a href="/arastirma">🔬 Re-Research</a></div>
__BODY__
</body></html>"""
    return tpl.replace("__BODY__", body)
