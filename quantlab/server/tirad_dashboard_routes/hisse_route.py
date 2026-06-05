

# ════════════════════════════════════════════════════════════════════════════
# EK SEKME: /hisse — BOT 3 hisse momentum manuel sinyali (Trade The Pool / hisse prop)
# equity_signal.py'nin yazdığı paper/equity_signal.json'u gösterir. (additive. Claude.)
# ════════════════════════════════════════════════════════════════════════════
@app.route("/hisse")
@requires_auth
def hisse_panel():
    import json
    import os
    import html as _h

    def esc(x):
        return _h.escape(str(x)) if x is not None else "—"

    path = os.path.join(PAPER_DIR, "equity_signal.json") if "PAPER_DIR" in globals() else "/root/tirad/paper/equity_signal.json"
    try:
        r = json.load(open(path))
    except Exception:
        r = None
    if not r:
        body = "<p class=muted>Henüz hisse sinyali yok. <code>equity_signal.py</code> çalışınca görünür.</p>"
    else:
        rows = "".join(
            f"<tr><td style='color:{'#3fb950' if p.get('action')=='AÇ' else '#8b949e'};font-weight:700'>{esc(p.get('action'))}</td>"
            f"<td><b>{esc(p.get('ticker'))}</b></td><td><b>{esc(p.get('shares'))} adet</b> (${esc(p.get('usd'))})</td>"
            f"<td>${esc(p.get('entry'))}</td><td>${esc(p.get('stop'))} <span class=muted>(%{esc(p.get('stop_pct'))})</span></td>"
            f"<td>${esc(p.get('risk_usd'))}</td><td>{p.get('mom90_pct'):+.0f}%</td></tr>"
            for p in (r.get("positions") or []))
        closes = "".join(
            f"<tr><td style='color:#f85149;font-weight:700'>KAPAT</td><td colspan=6 class=muted><b>{esc(c.get('ticker'))}</b> — sinyalden çıktı, kapat</td></tr>"
            for c in (r.get("closes") or []))
        ok = r.get("risk_ok")
        rc = "#3fb950" if ok else "#f85149"
        body = f"""
<div class=badge>BOT 3 — Hisse Momentum · long-only Top-{esc(r.get('topk'))} · ${esc(r.get('account'))} hesap</div>
<div class=badge style="border-color:{rc}">Deploy ${esc(r.get('deployed_usd'))} · Toplam-risk <span style="color:{rc}">${esc(r.get('total_risk_usd'))}</span> / DD-bütçe ${esc(r.get('dd_budget_usd'))} (%4) {'✓' if ok else '⚠️'}</div>
<p class=note>{esc(r.get('note'))}</p>
<table><tr><th>Aksiyon</th><th>Hisse</th><th>AL (adet/$)</th><th>Giriş≈</th><th>Stop-loss (zorunlu)</th><th>Risk $</th><th>90g mom</th></tr>
{rows}{closes}</table>
<p class=muted style="margin-top:12px">Son güncelleme: {esc(r.get('ts'))} · MANUEL — Trade The Pool/hisse prop platformunda elle gir.
Kanıtlı edge (OOS Sharpe 1.66) ama 2023-26 boğası + survivorship şişkin → ileriye haircut'lı bekle.</p>
"""
    tpl = """<!doctype html><html lang=tr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>TIRAD — Hisse Momentum (Bot 3)</title>
<style>body{background:#0d1117;color:#e6edf3;font-family:system-ui,Arial;margin:0;padding:16px}
a{color:#58a6ff}h1{font-size:20px}table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:6px 9px;border-bottom:1px solid #21262d;text-align:left}th{color:#8b949e}
.muted{color:#8b949e}.sub{color:#8b949e;font-size:12px;margin-bottom:10px}
.badge{display:inline-block;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:6px 12px;margin:6px 0;font-weight:600}
.note{background:#161b22;padding:10px 12px;border-radius:8px;font-size:12px;color:#c9d1d9}</style></head><body>
<h1>📈 TIRAD — Bot 3: Hisse Momentum (manuel)</h1>
<div class=sub>Kanıtlı edge, crypto'ya ortogonal · <a href="/">🏠</a> · <a href="/sinyal">📡 Crypto</a> · <a href="/forex">💱 FX</a> · <a href="/bybit">🟡 Bybit</a></div>
__BODY__
</body></html>"""
    return tpl.replace("__BODY__", body)
