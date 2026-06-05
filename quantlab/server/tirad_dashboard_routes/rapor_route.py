

# ════════════════════════════════════════════════════════════════════════════
# EK SEKME: /rapor — kâr sıralaması + güncel kararlar + işlem geçmişi
# (additive; mevcut route'lara dokunmaz. Eklenme: Claude.)
# ════════════════════════════════════════════════════════════════════════════
@app.route("/rapor")
@requires_auth
def rapor():
    import html as _h

    def esc(x):
        return _h.escape(str(x)) if x is not None else "—"

    def navpct(b):
        s = b.get("stats") or {}
        se = float(b.get("start_eq") or 1000.0)
        return (float(s.get("navnow", se)) / se - 1.0) * 100.0 if se else 0.0

    bots = sorted(load_paper_bots(), key=navpct, reverse=True)

    # 1) kâr sıralaması
    rk = []
    for i, b in enumerate(bots, 1):
        s = b.get("stats") or {}
        ref = b.get("ref") or {}
        p = navpct(b)
        col = "#3fb950" if p >= 0 else "#f85149"
        bsharpe = f"{ref['oos_sharpe']:.2f}" if ref.get("oos_sharpe") is not None else "—"
        rk.append(
            f"<tr><td>{i}</td><td>{esc(b.get('title') or b.get('key'))}</td>"
            f"<td>{esc(b.get('family',''))}</td>"
            f"<td>${float(s.get('navnow', b.get('start_eq', 1000))):,.2f}</td>"
            f"<td style='color:{col}'>{p:+.2f}%</td><td>{esc(s.get('days','—'))}</td>"
            f"<td class=muted>{bsharpe}</td></tr>")
    RANK = "".join(rk) or "<tr><td colspan=7 class=muted>veri yok</td></tr>"

    # 2) güncel kararlar (hangi coin / hangi yön / hangi kol)
    dec = []
    for b in bots:
        tg = b.get("targets") or {}
        parts = [f"<b>{esc(k)}</b>: {esc(', '.join(v))}" for k, v in tg.items() if v]
        dec.append(f"<tr><td>{esc(b.get('title') or b.get('key'))}</td>"
                   f"<td>{' &nbsp;|&nbsp; '.join(parts) or '<span class=muted>pozisyon yok</span>'}</td></tr>")
    DEC = "".join(dec)

    # 3) işlem geçmişi (testnet executor — live_bot.db trades)
    conn = _open_db()
    trades = []
    if conn and _table_exists(conn, "trades"):
        trades = _rows_to_dicts(
            conn, "SELECT bot,coin,dir,entry,exit,lev,rr,pnl,opened,closed,mode "
            "FROM trades ORDER BY rowid DESC LIMIT 200")
    th = []
    for t in trades:
        d = "LONG" if (t.get("dir") or 0) > 0 else "SHORT"
        pnl = t.get("pnl")
        pcol = "#3fb950" if (pnl or 0) >= 0 else "#f85149"
        pnls = f"{pnl:+.2f}" if pnl is not None else "—"
        th.append(
            f"<tr><td>{esc(t.get('bot'))}</td><td>{esc(t.get('coin'))}</td><td>{d}</td>"
            f"<td>{esc(t.get('opened'))}</td><td>{esc(t.get('closed'))}</td>"
            f"<td>{esc(t.get('entry'))}</td><td>{esc(t.get('exit'))}</td>"
            f"<td>{esc(t.get('lev'))}x</td><td style='color:{pcol}'>{pnls}</td></tr>")
    TRADES = "".join(th) or ("<tr><td colspan=9 class=muted>Henüz kapanmış işlem yok — "
                             "testnet executor işlem açıp kapatınca coin/saat/yön/K-Z burada görünür.</td></tr>")

    tpl = """<!doctype html><html lang=tr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>TIRAD — Rapor</title>
<style>body{background:#0d1117;color:#e6edf3;font-family:system-ui,Arial;margin:0;padding:16px}
a{color:#58a6ff}h1{font-size:20px}h2{font-size:15px;margin-top:26px;border-bottom:1px solid #30363d;padding-bottom:6px}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:6px 9px;border-bottom:1px solid #21262d;text-align:left}
th{color:#8b949e;font-weight:600}.muted{color:#8b949e}.sub{color:#8b949e;font-size:12px;margin-bottom:8px}</style></head><body>
<h1>📊 TIRAD — Rapor &amp; İşlem Geçmişi</h1>
<div class=sub>Paper/testnet · canlı · <a href="/">🏠 Tüm Botlar</a></div>
<h2>🏆 Kâr Sıralaması (canlı NAV)</h2>
<table><tr><th>#</th><th>Bot</th><th>Aile</th><th>NAV $</th><th>NAV %</th><th>Gün</th><th>Backtest Sharpe</th></tr>__RANK__</table>
<h2>🎯 Güncel Kararlar — hangi coin / hangi yön / hangi kol</h2>
<table><tr><th>Bot</th><th>Hedef pozisyonlar</th></tr>__DEC__</table>
<h2>📜 İşlem Geçmişi — coin · açılış/kapanış saati · yön · kaldıraç · K/Z</h2>
<table><tr><th>Bot</th><th>Coin</th><th>Yön</th><th>Açılış</th><th>Kapanış</th><th>Giriş</th><th>Çıkış</th><th>Kald.</th><th>PnL $</th></tr>__TRADES__</table>
<p class=muted style="margin-top:24px">⚠️ Paper-trade — gerçek para yok. Çok erken; yargı için haftalar gerek.</p>
</body></html>"""
    return tpl.replace("__RANK__", RANK).replace("__DEC__", DEC).replace("__TRADES__", TRADES)
