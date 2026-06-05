#!/usr/bin/env python3
"""
live_strategy.py — ÜRETİM BEYNİ (backtest ile birebir, canlıda son bara uygular)
═══════════════════════════════════════════════════════════════════════
Doğrulanmış sistem: donchian + supertrend trend sinyali → meta-label kalite
filtresi → confidence-weighted fractional Kelly boyutlama.
Pür fonksiyon: girdi {coin: df}, çıktı entry kararları. Test edilebilir.
"""
import pickle, numpy as np, os
import warnings; warnings.filterwarnings("ignore")
from signal_lab import atr
from meta_label import feat_arrays, FEATURES
import sig_donchian_breakout as D, sig_supertrend_regime as S

# backtest'te doğrulanan en iyi configler
DONCHIAN = D.make_sig(40, "atr", 0.25, 0.0)
SUPERTREND = S.make_sig(10, 3, 25)
SL_ATR = 2.0
TP_R = 2.75   # donchian 2.5 / supertrend 3.0 ortalaması
BASE_RISK = 0.015      # fractional-Kelly proxy (~quarter Kelly)
MAX_RISK = 0.03

_M = None
def _model():
    global _M
    if _M is None and os.path.exists("meta_model.pkl"):
        _M = pickle.load(open("meta_model.pkl", "rb"))
    return _M

def signals_at_last(df):
    """Son kapanmış barda hangi stratejiler hangi yönde sinyal veriyor?"""
    out = {}
    for name, sig in [("donchian", DONCHIAN), ("supertrend", SUPERTREND)]:
        pos = sig(df)
        if len(pos) and pos[-1] != 0:
            out[name] = int(pos[-1])
    return out

def decide(df, in_position=False):
    """Tek coin için entry kararı. df: son ~400+ 4H bar. Dönüş: dict|None."""
    if in_position or len(df) < 250:
        return None
    sigs = signals_at_last(df)
    if not sigs:
        return None
    # yön: iki strateji aynı yöndeyse güçlü; çelişirse atla
    dirs = set(sigs.values())
    if len(dirs) > 1:
        return None
    d = dirs.pop()
    c = df["close"].to_numpy(float); a = atr(df, 14)
    entry = float(c[-1])                      # canlıda ~ sıradaki açılış; replay'de son kapanış
    at = float(a[-1]) if a[-1] > 0 else entry*0.01
    risk_px = SL_ATR * at
    sl = entry - d*risk_px
    tp = entry + d*TP_R*risk_px
    sl_dist = risk_px/entry
    if not (0.003 < sl_dist < 0.12):
        return None
    # meta-label skoru (giriş-anı feature'ları = son bar)
    M = _model(); proba = None
    if M:
        fa = feat_arrays(df); fi = len(df)-1
        row = [float(fa[f][fi]) if f in fa and np.isfinite(fa[f][fi]) else np.nan for f in FEATURES[:10]]
        row += [d, sl_dist]                   # dir, sl_dist (FEATURES son ikisi)
        proba = float(M["model"].predict_proba(np.array([row]))[:,1][0])
        if proba < M["threshold"]:
            return None                        # meta-filtre eledi
    # confidence-weighted boyut (orijinal fikir): yüksek proba → büyük risk
    risk_pct = BASE_RISK
    if proba is not None:
        risk_pct = min(MAX_RISK, BASE_RISK * (0.5 + proba/M["threshold"]*0.5))
    return {"dir": "LONG" if d == 1 else "SHORT", "d": d, "entry": entry, "sl": sl, "tp": tp,
            "atr": at, "sl_dist": sl_dist, "proba": proba, "risk_pct": risk_pct,
            "strats": list(sigs.keys())}

if __name__ == "__main__":
    # hızlı duman testi: mktdata son barında kaç sinyal?
    from signal_lab import load_all
    dfs = load_all("mktdata", "4h"); fired = 0
    for c, df in dfs.items():
        dec = decide(df.iloc[-400:])
        if dec:
            fired += 1
            print(f"  {c}: {dec['dir']} entry={dec['entry']:.4f} proba={dec['proba']} risk%={dec['risk_pct']*100:.2f} {dec['strats']}")
    print(f"Son barda {fired} coin'de entry sinyali (meta-filtre sonrası).")
