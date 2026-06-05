

# ════════════════════════════════════════════════════════════════════════════
# EK SEKME: /saglik — canlı↔backtest sapma / sağlık (overfit dedektörü)
# (additive. Eklenme: Claude.)
# ════════════════════════════════════════════════════════════════════════════
def _bot_health(b):
    """Returns (emoji, level, reason). Honest + early-aware (az işlemde alarm verme)."""
    s = b.get("stats") or {}
    ref = b.get("ref") or {}
    se = float(b.get("start_eq") or 1000.0)
    nav = float(s.get("navnow", se))
    navpct = (nav / se - 1.0) * 100.0 if se else 0.0
    days = int(s.get("days", 0) or 0)
    # canlı drawdown'ı NAV eğrisinden hesapla
    curve = [float(p.get("v", se)) for p in (b.get("nav") or []) if isinstance(p, dict)]
    live_mdd = 0.0
    if curve:
        peak = curve[0]
        for v in curve:
            peak = max(peak, v)
            live_mdd = min(live_mdd, v / peak - 1.0)
    live_mdd *= 100.0
    ref_mdd = (ref.get("oos_maxdd") or 0.0) * 100.0  # negatif
    # kurallar (sermaye-tabanı > drawdown > erken > sapma)
    if nav < 0.85 * se:
        return "🔴", "RED", f"Kasa %15+ düştü (${nav:,.0f}) — DUR"
    if days >= 3 and ref_mdd < 0 and live_mdd <= ref_mdd * 1.5:
        return "🔴", "RED", f"Drawdown backtest'i çok aştı ({live_mdd:.0f}% vs ref {ref_mdd:.0f}%)"
    if days < 5:
        return "🟢", "GREEN", f"Erken ({days}g) — varyans normal, izlemeye devam"
    if days >= 3 and ref_mdd < 0 and live_mdd <= ref_mdd:
        return "🟡", "YELLOW", f"Drawdown backtest seviyesinde ({live_mdd:.0f}%) — izle"
    if navpct < -8.0:
        return "🟡", "YELLOW", f"NAV beklentinin altında ({navpct:+.1f}%) — izle"
    return "🟢", "GREEN", "Canlı, backtest beklentisiyle uyumlu"


@app.route("/saglik")
@requires_auth
def saglik():
    import html as _h

    def esc(x):
        return _h.escape(str(x)) if x is not None else "—"

    bots = load_paper_bots()
    n_green = n_yellow = n_red = 0
    rows = []
    for b in sorted(bots, key=lambda x: (x.get("stats") or {}).get("navnow", 0), reverse=True):
        emoji, level, reason = _bot_health(b)
        n_green += level == "GREEN"
        n_yellow += level == "YELLOW"
        n_red += level == "RED"
        s = b.get("stats") or {}
        ref = b.get("ref") or {}
        se = float(b.get("start_eq") or 1000.0)
        navpct = (float(s.get("navnow", se)) / se - 1.0) * 100.0
        col = "#3fb950" if navpct >= 0 else "#f85149"
        bs = f"{ref['oos_sharpe']:.2f}" if ref.get("oos_sharpe") is not None else "—"
        rows.append(
            f"<tr><td>{emoji}</td><td>{esc(b.get('title') or b.get('key'))}</td>"
            f"<td style='color:{col}'>{navpct:+.2f}%</td><td>{esc(s.get('days','—'))}</td>"
            f"<td class=muted>backtest Sharpe {bs}</td><td>{esc(reason)}</td></tr>")
    BODY = "".join(rows)
    banner = f"🟢 {n_green}  ·  🟡 {n_yellow}  ·  🔴 {n_red}  (toplam {len(bots)} bot)"

    tpl = """<!doctype html><html lang=tr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>TIRAD — Sağlık</title>
<style>body{background:#0d1117;color:#e6edf3;font-family:system-ui,Arial;margin:0;padding:16px}
a{color:#58a6ff}h1{font-size:20px}table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:6px 9px;border-bottom:1px solid #21262d;text-align:left}th{color:#8b949e}
.muted{color:#8b949e}.sub{color:#8b949e;font-size:12px;margin-bottom:10px}
.banner{font-size:16px;margin:10px 0;padding:8px 12px;background:#161b22;border-radius:8px;display:inline-block}</style></head><body>
<h1>🩺 TIRAD — Sağlık / Canlı↔Backtest Sapma</h1>
<div class=sub>Overfit/edge-bozulma erken-uyarı · <a href="/">🏠</a> · <a href="/rapor">📊 Rapor</a> · <a href="/piyasa">📈 Piyasa</a></div>
<div class=banner>__BANNER__</div>
<table><tr><th></th><th>Bot</th><th>NAV %</th><th>Gün</th><th>Referans</th><th>Durum</th></tr>__BODY__</table>
<p class=muted style="margin-top:20px">Kural: kasa &lt;%85→🔴 · drawdown backtest'i aşarsa→🟡/🔴 · &lt;5 gün→🟢 (erken, varyans normal). Yargı için haftalar gerek.</p>
</body></html>"""
    return tpl.replace("__BANNER__", banner).replace("__BODY__", BODY)
