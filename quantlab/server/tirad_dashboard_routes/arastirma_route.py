

# ════════════════════════════════════════════════════════════════════════════
# EK SEKME: /arastirma — zamanlanmış re-research raporu (RAPOR-ONLY, insan-kapılı)
# research_runner.py'nin yazdığı paper/research.json'u gösterir. (additive. Claude.)
# ════════════════════════════════════════════════════════════════════════════
@app.route("/arastirma")
@requires_auth
def arastirma():
    import json
    import os
    import html as _h

    def esc(x):
        return _h.escape(str(x)) if x is not None else "—"

    path = os.path.join(PAPER_DIR, "research.json") if "PAPER_DIR" in globals() else "/root/tirad/paper/research.json"
    try:
        r = json.load(open(path))
    except Exception:
        r = None

    if not r:
        body = ("<p class=muted>Henüz re-research raporu yok. Haftalık cron "
                "(<code>research_runner.py</code>) ilk çalıştığında burada görünür.</p>")
    else:
        review = r.get("needs_review")
        banner_col = "#f0a020" if review else "#3fb950"
        banner_txt = ("🟠 GÖZDEN GEÇİR" if review else "🟢 STABİL — aksiyon yok")
        rows = "".join(
            f"<tr><td>{esc(p.get('key'))}</td><td>{esc(p.get('navnow'))}</td>"
            f"<td>{esc(p.get('days'))}</td><td>{esc(p.get('fwd_sharpe'))}</td>"
            f"<td class=muted>{esc(p.get('ref_sharpe'))}</td>"
            f"<td>{'⚠️ sapma' if p.get('decay_flag') else '✓'}</td></tr>"
            for p in r.get("paper", []))
        edge = "✅ GERÇEK" if r.get("edge_real") else "⚠️ ZAYIF"
        drift = "⚠️ KAYDI" if r.get("param_drift") else "✓ sabit"
        body = f"""
<div class=banner style="background:{banner_col};color:#0d1117">{banner_txt}</div>
<p class=verdict>{esc(r.get('verdict'))}</p>
<h3>Overfit dürüstlük geçidi</h3>
<table>
<tr><th>Metrik</th><th>Değer</th><th>Yorum</th></tr>
<tr><td>Deflated Sharpe (DSR)</td><td>{esc(r.get('dsr'))}</td><td class=muted>&gt;0.95 = edge gerçek</td></tr>
<tr><td>PBO</td><td>{esc(r.get('pbo'))}</td><td class=muted>&lt;0.5 = OOS'ta genelleşiyor</td></tr>
<tr><td>Gözlenen vs null Sharpe (yıllık)</td><td>{esc(r.get('obs_sharpe_ann'))} vs {esc(r.get('null_sharpe_ann'))}</td><td class=muted>seçim-yanlılığı tabanı</td></tr>
<tr><td>Edge durumu</td><td>{edge}</td><td class=muted>DSR&amp;PBO birlikte</td></tr>
</table>
<h3>Walk-forward parametre-drift</h3>
<table>
<tr><th>Deploy edilen</th><th>WF en iyi (son 12ay)</th><th>Durum</th></tr>
<tr><td>{esc(r.get('deployed'))}</td><td>{esc(r.get('wf_best'))}</td><td>{drift}</td></tr>
</table>
<h3>Paper ↔ Backtest sapma (edge çöküşü erken-uyarı)</h3>
<table>
<tr><th>Bot</th><th>NAV</th><th>Gün</th><th>Canlı Sharpe</th><th>Ref OOS</th><th>Durum</th></tr>
{rows}
</table>
<p class=muted style="margin-top:14px">⚠️ Bu rapor SADECE bilgilendirir — parametre OTOMATİK DEĞİŞTİRİLMEZ.
Deploy kararı insana aittir (overfit/sessiz-çöküş koruması). Son güncelleme: {esc(r.get('ts'))}.</p>
"""

    tpl = """<!doctype html><html lang=tr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>TIRAD — Re-Research</title>
<style>body{background:#0d1117;color:#e6edf3;font-family:system-ui,Arial;margin:0;padding:16px}
a{color:#58a6ff}h1{font-size:20px}h3{margin-top:20px}table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:6px 9px;border-bottom:1px solid #21262d;text-align:left}th{color:#8b949e}
.muted{color:#8b949e}.sub{color:#8b949e;font-size:12px;margin-bottom:10px}
.banner{font-size:15px;margin:10px 0;padding:8px 12px;border-radius:8px;display:inline-block;font-weight:600}
.verdict{background:#161b22;padding:10px 12px;border-radius:8px;font-size:13px}</style></head><body>
<h1>🔬 TIRAD — Zamanlanmış Re-Research (rapor-only)</h1>
<div class=sub>Haftalık kendini-değerlendirme · DEPLOY ETMEZ · <a href="/">🏠</a> · <a href="/rapor">📊 Rapor</a> · <a href="/saglik">🩺 Sağlık</a> · <a href="/piyasa">📈 Piyasa</a></div>
__BODY__
</body></html>"""
    return tpl.replace("__BODY__", body)
