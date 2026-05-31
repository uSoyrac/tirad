#!/usr/bin/env python3
"""
pairs_trade.py — STATİSTİKSEL ARBİTRAJ (cointegration pairs trading)
═══════════════════════════════════════════════════════════════════════
Trend'den FARKLI, market-nötr edge: iki cointegrated coin'in spread'i geçici
sapınca ortalamaya dönüşünü ticaret eder. Walk-forward SIZINTISIZ:
  - çiftler + hedge ratio SADECE train (ilk %60) verisinde seçilir
  - z-skor causal (rolling), ticaret SADECE test (son %40) diliminde
  - maliyet: her bacak fee+slippage (2 bacak giriş + 2 bacak çıkış)
Ölçer: per-trade getiri, Sharpe, frekans, OOS stabilite, TREND ile korelasyon.
"""
import json, itertools, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from statsmodels.tsa.stattools import coint
from signal_lab import load_all

COST_LEG = 0.0004 + 0.0003     # fee + slippage per bacak
ENTRY_Z = 2.0; EXIT_Z = 0.5; STOP_Z = 4.0; ZWIN = 30

def build_panel(coins=None):
    dfs = load_all("mktdata","4h")
    if coins: dfs = {c:dfs[c] for c in coins if c in dfs}
    panel = pd.DataFrame({c: np.log(df["close"]) for c,df in dfs.items()}).dropna()
    return panel

def select_pairs(train, pmax=0.02):
    cols = list(train.columns); pairs = []
    for a,b in itertools.combinations(cols,2):
        try:
            _,p,_ = coint(train[a], train[b])
        except Exception: continue
        if p < pmax:
            beta = np.polyfit(train[b], train[a], 1)[0]   # hedge ratio (train OLS)
            pairs.append((a,b,beta,p))
    return pairs

def trade_pair(a,b,beta, test):
    spread = test[a] - beta*test[b]
    z = (spread - spread.rolling(ZWIN).mean())/(spread.rolling(ZWIN).std()+1e-12)
    z = z.values; sp = spread.values; idx = test.index
    trades=[]; pos=0; entry_sp=0; entry_i=0
    for i in range(ZWIN, len(z)):
        if pos==0:
            if z[i] > ENTRY_Z: pos=-1; entry_sp=sp[i]; entry_i=i      # short spread (A pahalı)
            elif z[i] < -ENTRY_Z: pos=1; entry_sp=sp[i]; entry_i=i    # long spread
        else:
            exit_now = abs(z[i])<EXIT_Z or abs(z[i])>STOP_Z or i==len(z)-1
            if exit_now:
                ret = pos*(sp[i]-entry_sp) - 4*COST_LEG   # 2 bacak giriş+2 çıkış
                trades.append({"r": float(ret), "exit_ts": str(idx[i]), "pair": f"{a}/{b}"})
                pos=0
    return trades

def stats(trades, bars_yr=6*365):
    if len(trades)<5: return None
    r=np.array([t["r"] for t in trades])
    sh=r.mean()/(r.std()+1e-9)*np.sqrt(len(r)/ (1))  # işlem-bazlı Sharpe yaklaşığı
    return {"n":len(r),"wr":(r>0).mean()*100,"avg":r.mean()*100,"sum":r.sum()*100,
            "sharpe_trade":r.mean()/(r.std()+1e-9)}

LONG = ["BTC","ETH","SOL","BNB","XRP","ADA","AVAX","DOGE","LINK","DOT","LTC","ATOM","NEAR","INJ","FIL","ETC","UNI"]
def main():
    panel = build_panel(LONG)            # uzun-geçmiş coinler (2021→2026)
    n=len(panel); split=int(n*0.6)
    train, test = panel.iloc[:split], panel.iloc[split:]
    print("="*78); print(f"  STATARB PAIRS TRADING — {panel.shape[1]} coin, train {train.index[0].date()}→{train.index[-1].date()}, test→{test.index[-1].date()}"); print("="*78)
    pairs = select_pairs(train)
    print(f"  Train'de cointegrated çift (p<0.02): {len(pairs)}")
    if not pairs: print("  Çift yok."); return
    print("  En güçlü 8:", [f"{a}/{b}(p={p:.3f})" for a,b,_,p in sorted(pairs,key=lambda x:x[3])[:8]])
    all_tr=[]
    for a,b,beta,p in pairs:
        all_tr += trade_pair(a,b,beta,test)
    s=stats(all_tr)
    print(f"\n  OOS (test, sızıntısız) — tüm çiftler havuzu:")
    if s:
        all_tr.sort(key=lambda x:x["exit_ts"]); h=len(all_tr)//2
        s1=stats(all_tr[:h]); s2=stats(all_tr[h:])
        print(f"    N={s['n']}  WR={s['wr']:.1f}%  ort getiri={s['avg']:+.3f}%/işlem  toplam={s['sum']:+.1f}%  trade-Sharpe={s['sharpe_trade']:+.3f}")
        print(f"    zaman: ilk½ ort={s1['avg'] if s1 else 0:+.3f}%  son½ ort={s2['avg'] if s2 else 0:+.3f}%")
        # basit equity (her trade eşit %2 sermaye)
        eq=100.0
        for t in all_tr: eq*= (1+0.5*t["r"])   # 0.5x ölçek (spread getirisi zaten oransal)
        print(f"    kabaca equity (0.5x ölçek): ${eq:.0f}")
        verdict = "POZİTİF market-nötr edge ✓" if s["avg"]>0 and (s2 and s2["avg"]>0) else "OOS'ta dayanmıyor/negatif"
        print(f"    VERDICT: {verdict}")
        json.dump(all_tr, open("/tmp/pairs_trades.json","w"))
    else:
        print("    Yetersiz işlem.")

if __name__=="__main__":
    main()
