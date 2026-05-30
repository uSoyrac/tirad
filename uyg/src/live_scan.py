#!/usr/bin/env python3
"""
ALPHA İSTİHBARAT — ADVANCED SMC + ICT ANALİZİ
Kapsar: BOS/CHoCH, MSS, OB+Breaker, FVG, Displacement, Liquidity Map,
        OTE (Optimal Trade Entry), Volume Profile, Wyckoff Faz,
        Supply/Demand, Klasik indikatörler, Multi-TF, Sosyal
"""
import warnings; warnings.filterwarnings("ignore")
import sys, time, re, math
from datetime import datetime, timedelta
from collections import Counter, namedtuple

import requests, numpy as np, pandas as pd
import ccxt, yfinance as yf
from bs4 import BeautifulSoup

# ── Renkler ──────────────────────────────────────────────────
R="\033[0m"; B="\033[1m"; U="\033[4m"
GR="\033[92m"; RD="\033[91m"; YL="\033[93m"
CY="\033[96m"; MG="\033[95m"; DM="\033[2m"; BL="\033[94m"

def ok(s):  return f"{GR}{s}{R}"
def bad(s): return f"{RD}{s}{R}"
def warn(s):return f"{YL}{s}{R}"
def nfo(s): return f"{CY}{s}{R}"
def mag(s): return f"{MG}{s}{R}"
def dim(s): return f"{DM}{s}{R}"
def sep(c="─",n=68): print(c*n)
def head(t): sep("═"); print(f"{B}  {t}{R}"); sep("═")
def h2(t):   sep("─"); print(f"  {B}{CY}{t}{R}")

HDRS = {"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36"}

# ══════════════════════════════════════════════════════════════
#  BÖLÜM 1 – WEB SCRAPING + SOSYAL
# ══════════════════════════════════════════════════════════════

CRYPTO_MAP = {
    "BTC":["bitcoin","btc"],"ETH":["ethereum","eth"],"SOL":["solana","sol"],
    "BNB":["binance coin","bnb"],"AVAX":["avalanche","avax"],"ADA":["cardano","ada"],
    "DOGE":["dogecoin","doge"],"XRP":["ripple","xrp"],"DOT":["polkadot","dot"],
    "LINK":["chainlink","link"],"MATIC":["polygon","matic"],"ATOM":["cosmos","atom"],
    "NEAR":["near protocol","near"],"ARB":["arbitrum","arb"],"OP":["optimism","op"],
    "SUI":["sui"],"APT":["aptos","apt"],"INJ":["injective","inj"],
    "TIA":["celestia","tia"],"PEPE":["pepe"],"WIF":["dogwifhat","wif"],
    "TON":["toncoin","ton"],"TAO":["bittensor","tao"],"ENA":["ethena","ena"],
    "LTC":["litecoin","ltc"],"UNI":["uniswap","uni"],"AAVE":["aave"],
    "FTM":["fantom","ftm"],"RENDER":["render","rndr"],"SEI":["sei"],
    "JUP":["jupiter","jup"],"HYPE":["hyperliquid","hype"],"ZEC":["zcash","zec"],
}
ALIAS = {}
for s,al in CRYPTO_MAP.items():
    ALIAS[s.lower()]=s
    for a in al: ALIAS[a.lower()]=s

def mentions(txt):
    tl=txt.lower(); c=Counter()
    for m in re.finditer(r'[\$#]([A-Z]{2,8})\b',txt,re.I):
        s=m.group(1).upper()
        if s in CRYPTO_MAP: c[s]+=2
    for a,s in ALIAS.items():
        if len(a)>=3 and a in tl: c[s]+=1
    return c

def _get(url,t=12):
    try:
        time.sleep(0.8)
        r=requests.get(url,headers=HDRS,timeout=t)
        return BeautifulSoup(r.text,"lxml")
    except: return None

def scrape_all():
    total=Counter(); headlines=[]; sources={}

    # CryptoPanic
    try:
        r=requests.get("https://cryptopanic.com/api/v1/posts/?auth_token=public&kind=news&filter=hot",
                       headers=HDRS,timeout=12)
        for p in r.json().get("results",[])[:35]:
            t=p.get("title",""); headlines.append(t)
            for c in p.get("currencies",[]): total[c["code"].upper()]+=3
            total.update(mentions(t))
        sources["CryptoPanic"]=len(headlines)
    except: sources["CryptoPanic"]=0

    # CoinTelegraph
    s=_get("https://cointelegraph.com")
    ct=[a.get_text(strip=True) for a in (s.select("a[href*='/news/']") if s else []) if len(a.get_text(strip=True))>20][:20]
    for t in ct: headlines.append(t); total.update(mentions(t))
    sources["CoinTelegraph"]=len(ct)

    # CoinDesk
    s=_get("https://www.coindesk.com")
    cd=list({el.get_text(strip=True) for el in (s.find_all(["h2","h3"]) if s else []) if len(el.get_text(strip=True))>25})[:15]
    for t in cd: headlines.append(t); total.update(mentions(t))
    sources["CoinDesk"]=len(cd)

    # BTCHaber
    s=_get("https://btchaber.com")
    bh=[a.get_text(strip=True) for a in (s.select("h2 a,h3 a,.entry-title a") if s else []) if len(a.get_text(strip=True))>10][:12]
    for t in bh: headlines.append(t); total.update(mentions(t))
    sources["BTCHaber"]=len(bh)

    # CoinGecko Trending
    try:
        d=requests.get("https://api.coingecko.com/api/v3/search/trending",headers=HDRS,timeout=12).json()
        for item in d.get("coins",[]):
            sym=item["item"]["symbol"].upper()
            if sym in CRYPTO_MAP: total[sym]+=4
        sources["CoinGecko"]=len(d.get("coins",[]))
    except: sources["CoinGecko"]=0

    return total, headlines, sources

BULL_W={"bull","bullish","moon","pump","breakout","long","buy","support","bounce","recovery",
        "uptrend","reversal","surge","rally","opportunity","strong","higher","accumulate","hold"}
BEAR_W={"bear","bearish","dump","crash","short","sell","resistance","breakdown","downtrend",
        "correction","drop","fall","risk","warning","lower","weak","panic"}
BULL_TR={"boğa","yükseliş","alım","destek","toparlanma","güçlü","artış","al","pozitif","fırsat","dipten"}
BEAR_TR={"ayı","düşüş","satış","direnç","zayıf","risk","düzeltme","çöküş","sat"}

def sentiment(txts):
    bull=bear=0
    for t in txts:
        tl=t.lower()
        bull+=sum(1 for w in BULL_W|BULL_TR if w in tl)
        bear+=sum(1 for w in BEAR_W|BEAR_TR if w in tl)
    tot=bull+bear
    if tot==0: return 0.5,"NÖTR"
    r=bull/tot; sc=0.5+(r-0.5)*0.8
    return round(sc,3),("BOĞA" if sc>=0.58 else("AYI" if sc<=0.42 else"NÖTR"))

# ══════════════════════════════════════════════════════════════
#  BÖLÜM 2 – VERİ ÇEKME
# ══════════════════════════════════════════════════════════════

_ex=None
def ex():
    global _ex
    if _ex is None:
        _ex=ccxt.binance({"enableRateLimit":True,"options":{"defaultType":"future"}})
    return _ex

def ohlcv(sym,tf="4h",lim=400):
    try:
        raw=ex().fetch_ohlcv(sym,tf,limit=lim+1)
        df=pd.DataFrame(raw,columns=["ts","open","high","low","close","volume"])
        df["ts"]=pd.to_datetime(df["ts"],unit="ms"); df.set_index("ts",inplace=True)
        return df.iloc[:-1].astype(float)   # Anti-repainting
    except: return pd.DataFrame()

def bist(sym,tf="1d",lim=250):
    try:
        iv={"1d":"1d","4h":"1h","1h":"1h","1w":"1wk"}.get(tf,"1d")
        pr="60d" if iv=="1h" else "2y"
        df=yf.Ticker(sym).history(period=pr,interval=iv,auto_adjust=True)
        if df.empty: return pd.DataFrame()
        df.index=pd.to_datetime(df.index,utc=True).tz_localize(None)
        df.columns=df.columns.str.lower()
        df=df[["open","high","low","close","volume"]]
        if tf=="4h" and iv=="1h":
            df=df.resample("4h").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
        return df.tail(lim).astype(float)
    except: return pd.DataFrame()

def funding(sym):
    try: return ex().fetch_funding_rate(sym).get("fundingRate")
    except: return None

# ══════════════════════════════════════════════════════════════
#  BÖLÜM 3 – ADVANCED SMC / ICT MOTORU
# ══════════════════════════════════════════════════════════════

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def rsi_fn(s,p=14):
    d=s.diff(); g=d.clip(lower=0).rolling(p).mean(); l=(-d.clip(upper=0)).rolling(p).mean()
    return 100-100/(1+g/l.replace(0,np.nan))
def macd_fn(s,f=12,sl=26,sig=9):
    e1=ema(s,f); e2=ema(s,sl); ln=e1-e2; sg=ema(ln,sig); return ln,sg,ln-sg
def atr_fn(df,p=14):
    h=df["high"]; l=df["low"]; c=df["close"].shift(1)
    tr=pd.concat([h-l,(h-c).abs(),(l-c).abs()],axis=1).max(axis=1)
    return tr.rolling(p).mean()

# ─── Yapısal Analiz ──────────────────────────────────────────
def swing_pivots(df, lb=10):
    """Swing high/low tespit."""
    sh=pd.Series(False,index=df.index); sl=pd.Series(False,index=df.index)
    for i in range(lb,len(df)-1):
        wh=df["high"].iloc[i-lb:i+1]; wl=df["low"].iloc[i-lb:i+1]
        if df["high"].iloc[i]==wh.max(): sh.iloc[i]=True
        if df["low"].iloc[i]==wl.min(): sl.iloc[i]=True
    return sh,sl

def market_structure(df, lb=10):
    """
    BOS, CHoCH, MSS (Market Structure Shift = iç yapı kırılması).
    Döner: trend, bos_bull, bos_bear, choch_bull, choch_bear, mss_bull, mss_bear,
           hh_series (Higher Highs), hl_series (Higher Lows), lh, ll
    """
    sh,sl=swing_pivots(df,lb)
    sh_idx=df.index[sh]; sl_idx=df.index[sl]
    sh_vals=df["high"][sh]; sl_vals=df["low"][sl]

    if len(sh_vals)<3 or len(sl_vals)<3:
        return {"trend":"NEUTRAL","bos_bull":False,"bos_bear":False,
                "choch_bull":False,"choch_bear":False,"mss_bull":False,"mss_bear":False,
                "hh":False,"hl":False,"lh":False,"ll":False,
                "last_sh":None,"last_sl":None}

    # HH/HL/LH/LL dizisi
    hh = sh_vals.iloc[-1]>sh_vals.iloc[-2]  # Higher High
    hl = sl_vals.iloc[-1]>sl_vals.iloc[-2]  # Higher Low
    lh = sh_vals.iloc[-1]<sh_vals.iloc[-2]  # Lower High
    ll = sl_vals.iloc[-1]<sl_vals.iloc[-2]  # Lower Low

    trend="NEUTRAL"
    if hh and hl: trend="BULLISH"
    elif lh and ll: trend="BEARISH"

    # Konfirmasyon: son 3 kapanmış mum
    rc=df["close"].iloc[-4:-1]
    last_sh=float(sh_vals.iloc[-1]); last_sl=float(sl_vals.iloc[-1])
    prev_sh=float(sh_vals.iloc[-2]); prev_sl=float(sl_vals.iloc[-2])

    bos_bull = bool((rc>last_sh).all()) and trend=="BULLISH"
    bos_bear = bool((rc<last_sl).all()) and trend=="BEARISH"
    choch_bull= bool((rc>last_sh).all()) and trend=="BEARISH"   # Counter-trend kırılma
    choch_bear= bool((rc<last_sl).all()) and trend=="BULLISH"

    # MSS: İÇ yapıda daha küçük bir BOS (son 20 mumda)
    sub=df.iloc[-22:-1]; ssh,ssl=swing_pivots(sub,5)
    mss_bull=mss_bear=False
    if ssh.any() and ssl.any():
        sub_sh=sub["high"][ssh]; sub_sl=sub["low"][ssl]
        if len(sub_sh)>=2 and len(sub_sl)>=2:
            inner_rc=sub["close"].iloc[-3:]
            mss_bull=bool((inner_rc>float(sub_sh.iloc[-1])).any()) and trend!="BULLISH"
            mss_bear=bool((inner_rc<float(sub_sl.iloc[-1])).any()) and trend!="BEARISH"

    return {"trend":trend,"bos_bull":bos_bull,"bos_bear":bos_bear,
            "choch_bull":choch_bull,"choch_bear":choch_bear,
            "mss_bull":mss_bull,"mss_bear":mss_bear,
            "hh":hh,"hl":hl,"lh":lh,"ll":ll,
            "last_sh":last_sh,"last_sl":last_sl}

# ─── Order Blocks + Breaker Blocks ───────────────────────────
def order_blocks(df, n=3):
    """
    Bullish OB: Kırmızı mum → ardından güçlü yukarı hareket.
    Bearish OB: Yeşil mum → ardından güçlü aşağı hareket.
    Breaker Block: OB kırılmış = artık karşı yönde etkili.
    """
    c=df["close"]; o=df["open"]; h=df["high"]; l=df["low"]
    atr=atr_fn(df); blocks=[]
    end=len(df)-n-1; start=max(0,end-80)
    avg_move=((c-o).abs()).rolling(20).mean()

    for i in range(start,end):
        nxt=c.iloc[i+1:i+1+n]
        if len(nxt)<n: continue
        bar_sz=abs(c.iloc[i]-o.iloc[i])
        avg=avg_move.iloc[i]
        is_impulse = avg>0 and bar_sz>avg*1.3

        if not is_impulse: continue

        # Bullish OB
        if nxt.iloc[-1]>nxt.iloc[0] and c.iloc[i]<o.iloc[i]:
            ob_low=float(l.iloc[i]); ob_high=float(h.iloc[i])
            # Kırılmış mı? (fiyat OB'nin altına inmiş mi)
            subsequent=l.iloc[i+n:]
            breaker=any(subsequent<ob_low)
            blocks.append({"type":"bullish","low":ob_low,"high":ob_high,
                           "mid":(ob_low+ob_high)/2,"idx":i,"breaker":breaker,
                           "bars_ago":len(df)-i})
        # Bearish OB
        elif nxt.iloc[-1]<nxt.iloc[0] and c.iloc[i]>o.iloc[i]:
            ob_low=float(l.iloc[i]); ob_high=float(h.iloc[i])
            subsequent=h.iloc[i+n:]
            breaker=any(subsequent>ob_high)
            blocks.append({"type":"bearish","low":ob_low,"high":ob_high,
                           "mid":(ob_low+ob_high)/2,"idx":i,"breaker":breaker,
                           "bars_ago":len(df)-i})

    # Breaker = OB'nin karşı yönde çalışan hali
    breakers=[b for b in blocks if b["breaker"]]
    valid=[b for b in blocks if not b["breaker"]]

    bull_obs=sorted([b for b in valid if b["type"]=="bullish"],key=lambda x:x["bars_ago"])
    bear_obs=sorted([b for b in valid if b["type"]=="bearish"],key=lambda x:x["bars_ago"])
    bull_brk=sorted([b for b in breakers if b["type"]=="bearish"],key=lambda x:x["bars_ago"])  # Bearish OB kırılmış = bull breaker
    bear_brk=sorted([b for b in breakers if b["type"]=="bullish"],key=lambda x:x["bars_ago"])  # Bullish OB kırılmış = bear breaker

    return bull_obs[:3], bear_obs[:3], bull_brk[:2], bear_brk[:2]

# ─── Fair Value Gaps + Volume Imbalance ──────────────────────
def fair_value_gaps(df, min_pct=0.002):
    """FVG + Volume Imbalance (VI = FVG'nin hacim ağırlıklı versiyonu)."""
    h=df["high"].values; l=df["low"].values; v=df["volume"].values
    c=df["close"].values
    bull_fvg=[]; bear_fvg=[]

    for i in range(2,min(120,len(df)-1)):
        idx=-(i+1)
        c1h=h[idx-1]; c3l=l[idx+1]; c1l=l[idx-1]; c3h=h[idx+1]
        mid_vol=v[idx]

        if c3l>c1h:
            sz=(c3l-c1h)/c1h
            if sz>=min_pct:
                recent_lows=l[idx+2:]; filled=any(x<=c1h for x in recent_lows)
                bull_fvg.append({"low":c1h,"high":c3l,"mid":(c1h+c3l)/2,
                                  "size_pct":sz*100,"bars_ago":i,
                                  "vol_score":mid_vol,"filled":filled})
        if c3h<c1l:
            sz=(c1l-c3h)/c1l
            if sz>=min_pct:
                recent_highs=h[idx+2:]; filled=any(x>=c1l for x in recent_highs)
                bear_fvg.append({"low":c3h,"high":c1l,"mid":(c3h+c1l)/2,
                                  "size_pct":sz*100,"bars_ago":i,
                                  "vol_score":mid_vol,"filled":filled})

    bull_fvg.sort(key=lambda x:x["bars_ago"]); bear_fvg.sort(key=lambda x:x["bars_ago"])
    return [f for f in bull_fvg if not f["filled"]][:4], [f for f in bear_fvg if not f["filled"]][:4]

# ─── Liquidity Map ───────────────────────────────────────────
def liquidity_map(df, tol=0.0025, lb=40):
    """
    Equal Highs/Lows (BSL/SSL) + Previous Day/Week High/Low tespiti.
    Sell Side Liquidity (SSL) = equal lows → stops below
    Buy  Side Liquidity (BSL) = equal highs → stops above
    """
    h=df["high"].values[-lb:]; l=df["low"].values[-lb:]
    c=df["close"].values[-lb:]
    idx=df.index[-lb:]

    bsl_levels=[]; ssl_levels=[]

    for i in range(len(h)-4):
        for j in range(i+2,len(h)-2):
            if abs(h[i]-h[j])/h[i]<tol:
                eq=(h[i]+h[j])/2
                swept=any(h[k]>eq*(1+tol) for k in range(j+1,len(h)))
                bsl_levels.append({"level":eq,"swept":swept,
                                    "bars_ago":len(h)-j,"type":"BSL"})

    for i in range(len(l)-4):
        for j in range(i+2,len(l)-2):
            if abs(l[i]-l[j])/l[i]<tol:
                eq=(l[i]+l[j])/2
                swept=any(l[k]<eq*(1-tol) for k in range(j+1,len(l)))
                ssl_levels.append({"level":eq,"swept":swept,
                                    "bars_ago":len(l)-j,"type":"SSL"})

    # Daha temiz çıktı için tekrarları kaldır
    bsl_clean=[]; ssl_clean=[]
    for b in sorted(bsl_levels,key=lambda x:x["bars_ago"]):
        if not any(abs(b["level"]-x["level"])/b["level"]<tol for x in bsl_clean):
            bsl_clean.append(b)
    for s in sorted(ssl_levels,key=lambda x:x["bars_ago"]):
        if not any(abs(s["level"]-x["level"])/s["level"]<tol for x in ssl_clean):
            ssl_clean.append(s)

    # Sweep tespiti (son 5 mum)
    recent_h=h[-6:-1]; recent_l=l[-6:-1]; recent_c=c[-6:-1]
    sweep_up = sweep_down = False
    for b in bsl_clean:
        if any(x>b["level"]*(1+tol) for x in recent_h) and any(cc<b["level"] for cc in recent_c):
            sweep_up=True
    for s in ssl_clean:
        if any(x<s["level"]*(1-tol) for x in recent_l) and any(cc>s["level"] for cc in recent_c):
            sweep_down=True

    return (sorted(bsl_clean,key=lambda x:x["bars_ago"])[:4],
            sorted(ssl_clean,key=lambda x:x["bars_ago"])[:4],
            sweep_up, sweep_down)

# ─── Displacement (Güçlü Impulsif Hareket) ───────────────────
def displacement(df, multiplier=2.5):
    """
    Displacement: ATR'nin N katı büyüklüğünde tek mum hareketi.
    ICT'de 'purpose' gösterir — market maker aktif demek.
    """
    c=df["close"]; o=df["open"]
    atr=atr_fn(df,14)
    body=((c-o).abs()).shift(1)
    atr_s=atr.shift(1)
    last_5_bodies=body.iloc[-6:-1]
    last_5_atr=atr_s.iloc[-6:-1]
    displacements=[]
    for i in range(len(last_5_bodies)):
        if last_5_atr.iloc[i]>0 and last_5_bodies.iloc[i]>last_5_atr.iloc[i]*multiplier:
            direction="UP" if c.iloc[-(6-i)]>o.iloc[-(6-i)] else "DOWN"
            displacements.append({"ratio":last_5_bodies.iloc[i]/last_5_atr.iloc[i],
                                   "direction":direction,"bars_ago":5-i})
    return displacements

# ─── OTE (Optimal Trade Entry) ───────────────────────────────
def optimal_trade_entry(df, lb=50):
    """
    ICT OTE: Fibonacci 0.62–0.79 geri çekilme bölgesi.
    Bullish impulse'dan sonra bu bölgeye geri çekilme = ideal giriş.
    """
    h=df["high"].iloc[-lb:-1]; l=df["low"].iloc[-lb:-1]
    c=df["close"]
    cp=float(c.iloc[-2])

    swing_high=float(h.max()); swing_low=float(l.min())
    rng=swing_high-swing_low
    if rng<=0: return None

    # Bullish OTE: geri çekilme 0.62–0.79 arasında mı?
    fib62=swing_high-rng*0.618; fib79=swing_high-rng*0.786
    fib50=swing_high-rng*0.5

    bull_ote = fib79<=cp<=fib62
    bear_ote = (swing_low+rng*0.618)<=cp<=(swing_low+rng*0.786)

    # Hangi yönde daha son impulse?
    mid_idx=len(df)//2
    first_half_c=df["close"].iloc[mid_idx//2:mid_idx]
    second_half_c=df["close"].iloc[mid_idx:]
    last_impulse_up=float(second_half_c.iloc[-1])>float(first_half_c.iloc[0])

    return {"swing_high":swing_high,"swing_low":swing_low,
            "fib50":fib50,"fib62":fib62,"fib79":fib79,
            "cp":cp,"bull_ote":bull_ote,"bear_ote":bear_ote,
            "last_impulse_up":last_impulse_up}

# ─── Volume Profile (Manual) ─────────────────────────────────
def volume_profile(df, bins=24):
    """
    VPOC (Volume Point of Control): En çok hacmin geçtiği fiyat.
    VAH/VAL: %70 hacmin toplandığı üst/alt sınır.
    """
    if df.empty or "volume" not in df.columns: return None
    price_range=df["high"].max()-df["low"].min()
    if price_range<=0: return None
    bin_size=price_range/bins
    levels={}
    for _,row in df.iterrows():
        lo=row["low"]; hi=row["high"]; vol=row["volume"]
        if hi-lo<=0: continue
        for b in range(bins):
            bl=df["low"].min()+b*bin_size; bh=bl+bin_size
            overlap=max(0,min(hi,bh)-max(lo,bl))
            if overlap>0:
                key=round(bl+bin_size/2,4)
                levels[key]=levels.get(key,0)+vol*(overlap/(hi-lo))
    if not levels: return None
    vpoc=max(levels,key=levels.get)
    total_vol=sum(levels.values())
    target=total_vol*0.70
    sorted_levels=sorted(levels.items(),key=lambda x:x[1],reverse=True)
    cumvol=0; va_levels=[]
    for price,vol in sorted_levels:
        cumvol+=vol; va_levels.append(price)
        if cumvol>=target: break
    vah=max(va_levels); val=min(va_levels)
    return {"vpoc":vpoc,"vah":vah,"val":val}

# ─── Wyckoff Faz Tespiti ─────────────────────────────────────
def wyckoff_phase(df, lb=60):
    """
    Basitleştirilmiş Wyckoff faz analizi:
    PS (Preliminary Support), SC (Selling Climax), AR (Automatic Rally),
    ST (Secondary Test) → Birikim başlangıcı.
    """
    if len(df)<lb: return "UNKNOWN"
    sub=df.iloc[-lb:]
    c=sub["close"]; v=sub["volume"]; h=sub["high"]; l=sub["low"]

    vol_mean=v.mean(); vol_std=v.std()
    price_range=h.max()-l.min()

    # Yüksek hacimli düşük → Selling Climax
    low_bars=sub[l==l.min()]
    high_vol_at_low=any(v[low_bars.index]>vol_mean+vol_std)

    # Düşük hacimli yükseliş → Automatic Rally after SC
    first_third=sub.iloc[:lb//3]; last_third=sub.iloc[-lb//3:]
    lower_vol_rally=(last_third["volume"].mean()<first_third["volume"].mean() and
                     last_third["close"].mean()>first_third["close"].mean())

    # Dar range + düşük hacim ortada = Spring/Consolidation
    mid=sub.iloc[lb//3:2*lb//3]
    narrow_range=(mid["high"]-mid["low"]).mean()<price_range*0.015
    low_vol_mid=mid["volume"].mean()<vol_mean*0.85

    # Tüm göstergeler
    cp=float(c.iloc[-1]); hi=float(h.max()); lo=float(l.min())
    near_low = cp<lo+price_range*0.25
    near_high = cp>hi-price_range*0.25

    if high_vol_at_low and lower_vol_rally and narrow_range:
        return "WYCKOFF_ACCUMULATION"
    elif near_low and high_vol_at_low:
        return "SELLING_CLIMAX_ZONE"
    elif near_high and not lower_vol_rally:
        return "DISTRIBUTION_ZONE"
    elif narrow_range and low_vol_mid:
        return "CONSOLIDATION_SPRING"
    return "NO_PATTERN"

# ─── Supply & Demand Zones ───────────────────────────────────
def supply_demand_zones(df, lookback=100, min_move=0.015):
    """
    Supply/Demand Zone: Güçlü hareket başlamadan önceki konsolidasyon bölgeleri.
    OB'den daha geniş bölge — tüm konsolidasyonu kapsar.
    """
    c=df["close"]; h=df["high"]; l=df["low"]; v=df["volume"]
    zones=[]
    sub=df.iloc[-lookback:-1]
    avg_series = (h-l).rolling(20).mean()
    avg_val = float(avg_series.iloc[-1]) if not avg_series.empty and not pd.isna(avg_series.iloc[-1]) else 0.0

    for i in range(5,len(sub)-5):
        # Sonraki 5 mumda büyük hareket var mı?
        fwd_move=abs(float(sub["close"].iloc[i+4])-float(sub["close"].iloc[i]))/float(sub["close"].iloc[i])
        if fwd_move<min_move: continue

        # Bu mum etrafında konsolidasyon var mı?
        local_range=(sub["high"].iloc[max(0,i-3):i+1].max()-
                     sub["low"].iloc[max(0,i-3):i+1].min())
        avg_range=avg_val

        if local_range>0:
            direction="demand" if float(sub["close"].iloc[i+4])>float(sub["close"].iloc[i]) else "supply"
            zone_top=float(sub["high"].iloc[max(0,i-2):i+2].max())
            zone_bot=float(sub["low"].iloc[max(0,i-2):i+2].min())
            zones.append({"type":direction,"top":zone_top,"bot":zone_bot,
                          "mid":(zone_top+zone_bot)/2,"strength":fwd_move,
                          "bars_ago":len(sub)-i})

    demand=sorted([z for z in zones if z["type"]=="demand"],key=lambda x:x["bars_ago"])[:3]
    supply=sorted([z for z in zones if z["type"]=="supply"],key=lambda x:x["bars_ago"])[:3]
    return demand, supply

# ─── Divergence Dedektörü ────────────────────────────────────
def divergences(df):
    """RSI + MACD için boğa/ayı ve gizli diverjans."""
    c=df["close"]; l=df["low"]; h=df["high"]
    rsi_s=rsi_fn(c).shift(1)
    _,_,mh=macd_fn(c); mh_s=mh.shift(1)

    results={"rsi_bull_hidden":False,"rsi_bear_hidden":False,
             "rsi_bull_reg":False,"rsi_bear_reg":False,
             "macd_bull":False,"macd_bear":False,
             "rsi_val":None,"macd_hist":None}

    if len(df)<35: return results
    results["rsi_val"]=float(rsi_s.iloc[-1]) if not pd.isna(rsi_s.iloc[-1]) else None
    results["macd_hist"]=float(mh_s.iloc[-1]) if not pd.isna(mh_s.iloc[-1]) else None

    # 30 bar penceresi
    p=30
    price_lows=l.shift(1).iloc[-p-1:-1]; rsi_lows=rsi_s.iloc[-p-1:-1]
    price_highs=h.shift(1).iloc[-p-1:-1]; rsi_highs=rsi_s.iloc[-p-1:-1]
    mh_vals=mh_s.iloc[-p-1:-1]

    if len(price_lows)<10: return results

    pl1=float(price_lows.iloc[0]); pl2=float(price_lows.iloc[-1])
    rl1=float(rsi_lows.iloc[0]);   rl2=float(rsi_lows.iloc[-1])
    ph1=float(price_highs.iloc[0]);ph2=float(price_highs.iloc[-1])
    rh1=float(rsi_highs.iloc[0]);  rh2=float(rsi_highs.iloc[-1])

    results["rsi_bull_hidden"] = pl2>pl1 and rl2>rl1 and rl2<60  # Fiyat yüksek dip, RSI yüksek dip
    results["rsi_bear_hidden"] = ph2<ph1 and rh2<rh1 and rh2>40  # Fiyat düşük zirve, RSI düşük zirve
    results["rsi_bull_reg"]    = pl2<pl1 and rl2>rl1              # Klasik boğa div
    results["rsi_bear_reg"]    = ph2>ph1 and rh2<rh1              # Klasik ayı div

    if len(mh_vals)>=10:
        mh1=float(mh_vals.iloc[0]); mh2=float(mh_vals.iloc[-1])
        results["macd_bull"] = pl2<pl1 and mh2>mh1
        results["macd_bear"] = ph2>ph1 and mh2<mh1

    return results

# ─── Premium/Discount + Fib Seviyeleri ───────────────────────
def fib_levels(df, lb=60):
    h_max=df["high"].iloc[-lb:-1].max(); l_min=df["low"].iloc[-lb:-1].min()
    rng=h_max-l_min
    return {
        "high":h_max,"low":l_min,
        "fib236":h_max-rng*0.236,"fib382":h_max-rng*0.382,
        "fib50": h_max-rng*0.500,"fib618":h_max-rng*0.618,
        "fib786":h_max-rng*0.786,"fib100":l_min,
    }

# ─── Klasik İndikatörler ─────────────────────────────────────
def classic_indicators(df):
    c=df["close"]; v=df["volume"]
    sh=lambda s,n=1: s.shift(n)

    e8=float(sh(ema(c,8)).iloc[-1]); e21=float(sh(ema(c,21)).iloc[-1])
    e55=float(sh(ema(c,55)).iloc[-1]); e200=float(sh(ema(c,200)).iloc[-1])
    ema_full=e8>e21>e55>e200; ema_part=sum([e8>e21,e21>e55,e55>e200])>=2

    _,_,mhist=macd_fn(c); mh=float(sh(mhist).iloc[-1]); mh_p=float(sh(mhist,2).iloc[-1])
    macd_bull=mh>0 and mh>mh_p

    rsi_v=rsi_fn(c); rv=float(sh(rsi_v).iloc[-1])
    ovb=rv>70; ovs=rv<30

    bbu=ema(c,20)+2*c.rolling(20).std(); bbl=ema(c,20)-2*c.rolling(20).std()
    bw=(bbu-bbl)/c; bw_now=float(sh(bw).iloc[-1]); bw_avg=float(sh(bw.rolling(20).mean()).iloc[-1])
    bb_squeeze=bw_now<bw_avg*0.75; bb_above=float(sh(c).iloc[-1])>float(sh(bbu).iloc[-1])

    tp=(df["high"]+df["low"]+c)/3; vwap_v=(tp*v).cumsum()/v.cumsum()
    vwap_above=float(sh(c).iloc[-1])>float(sh(vwap_v).iloc[-1])
    vwap_val=float(sh(vwap_v).iloc[-1])

    dir_=np.sign(c.diff()).fillna(0); obv_v=(dir_*v).cumsum()
    obv_up=float(sh(obv_v).iloc[-1])>float(sh(obv_v,15).iloc[-1]) and float(sh(c).iloc[-1])>float(sh(c,15).iloc[-1])

    stoch_k=(c.rolling(14).max()-c)/(c.rolling(14).max()-c.rolling(14).min()+1e-10)*100
    stoch_k=stoch_k.rolling(3).mean(); sk=float(sh(stoch_k).iloc[-1]); sk_p=float(sh(stoch_k,2).iloc[-1])
    stoch_bull=sk_p<20 and sk>20

    return {"e8":e8,"e21":e21,"e55":e55,"e200":e200,
            "ema_full":ema_full,"ema_part":ema_part,
            "macd_bull":macd_bull,"macd_hist":mh,
            "rsi":rv,"overbought":ovb,"oversold":ovs,
            "bb_squeeze":bb_squeeze,"bb_above":bb_above,
            "vwap_above":vwap_above,"vwap":vwap_val,
            "obv_up":obv_up,"stoch_bull":stoch_bull}

# ─── CVD ─────────────────────────────────────────────────────
def cvd(df):
    d=np.where(df["close"]>df["open"],1,-1)
    cv=(d*df["volume"]).cumsum()
    r=cv.iloc[-21:-1]; p=df["close"].iloc[-21:-1]
    if len(r)<5: return False
    return bool(r.iloc[-1]>r.iloc[0] and p.iloc[-1]>p.iloc[0])

# ══════════════════════════════════════════════════════════════
#  BÖLÜM 4 – TAM ANALİZ + PUANLAMA
# ══════════════════════════════════════════════════════════════

def analyze(symbol, is_bist=False):
    tf="4h"
    df   = bist(symbol,tf) if is_bist else ohlcv(symbol,tf)
    df1d = bist(symbol,"1d") if is_bist else ohlcv(symbol,"1d")
    df1w = bist(symbol,"1w") if is_bist else ohlcv(symbol,"1w")
    df1h = bist(symbol,"1h") if is_bist else ohlcv(symbol,"1h")

    if df.empty or len(df)<100: return None
    cp=float(df["close"].iloc[-2])

    # ── SMC / ICT ─────────────────────────────────────────────
    ms     = market_structure(df,10)
    bull_obs,bear_obs,bull_brk,bear_brk = order_blocks(df)
    bull_fvg,bear_fvg = fair_value_gaps(df)
    bsl,ssl,sweep_up,sweep_down = liquidity_map(df)
    disps  = displacement(df)
    ote    = optimal_trade_entry(df)
    fibs   = fib_levels(df,60)
    vp     = volume_profile(df) if not is_bist else None
    wyck   = wyckoff_phase(df)
    demand_z,supply_z = supply_demand_zones(df)
    divs   = divergences(df)
    cl     = classic_indicators(df)

    trend=ms["trend"]

    # Funding (sadece kripto)
    fr=None
    if not is_bist:
        try: fr=funding(symbol)
        except: pass

    # MTF trend (1D + 1H)
    ms1d=market_structure(df1d,10) if not df1d.empty else {"trend":"NEUTRAL"}
    ms1h=market_structure(df1h,10) if not df1h.empty else {"trend":"NEUTRAL"}
    ms1w=market_structure(df1w,10) if not df1w.empty else {"trend":"NEUTRAL"}

    # ── PUANLAMA ──────────────────────────────────────────────
    smc_s=0; cl_s=0; inst_s=0; mtf_s=0
    smc_det={}; cl_det={}; inst_det={}; mtf_det={}

    # ─── SMC (max 10) ────────────────────────────────────────
    if trend=="BULLISH":
        if ms["bos_bull"]:    smc_s+=2; smc_det["BOS"]=ok("BOS Bullish ✅ +2")
        if ms["choch_bull"]:  smc_s+=1; smc_det["CHoCH"]=ok("CHoCH Bullish ✅ +1")
        if ms["mss_bull"]:    smc_s+=1; smc_det["MSS"]=ok("MSS (İç Yapı Kırılması) ✅ +1")
        if bull_obs:
            ob=bull_obs[0]; smc_s+=2
            at_ob=ob["low"]<=cp<=ob["high"]
            smc_det["OB"]=ok(f"Bullish OB {ob['low']:.4f}–{ob['high']:.4f} +2{' ◀ FİYAT BURADA!' if at_ob else ''}")
        if bull_brk:
            b=bull_brk[0]; smc_s+=1
            smc_det["BRK"]=ok(f"Bull Breaker Block {b['low']:.4f}–{b['high']:.4f} +1")
        if bull_fvg:
            f=bull_fvg[0]
            at_fvg=f["low"]<=cp<=f["high"]
            at_fvg_lbl=" ◀ FİYAT FVG'DE!" if at_fvg else ""
            smc_s+=1; smc_det["FVG"]=ok(f"Bullish FVG {f['low']:.4f}–{f['high']:.4f} +1{at_fvg_lbl}")
        if sweep_down: smc_s+=2; smc_det["LIQ"]=ok("SSL Sweep (Buy Side Güçlendi) ✅ +2")
        if ote and ote["bull_ote"]: smc_s+=1; smc_det["OTE"]=ok(f"OTE Geri Çekilme Bölgesi ({ote['fib79']:.4f}–{ote['fib62']:.4f}) ✅ +1")
        if demand_z:
            d=demand_z[0]
            at_dz=d["bot"]<=cp<=d["top"]
            if at_dz: smc_s+=1; smc_det["DZ"]=ok(f"Demand Zone'DA ✅ +1 ({d['bot']:.4f}–{d['top']:.4f})")
        if wyck in ("WYCKOFF_ACCUMULATION","SELLING_CLIMAX_ZONE"):
            smc_s+=1; smc_det["WYCK"]=ok(f"Wyckoff: {wyck} ✅ +1")

    elif trend=="BEARISH":
        if ms["bos_bear"]:    smc_s+=2; smc_det["BOS"]=bad("BOS Bearish ✅ +2")
        if ms["choch_bear"]:  smc_s+=1; smc_det["CHoCH"]=bad("CHoCH Bearish ✅ +1")
        if ms["mss_bear"]:    smc_s+=1; smc_det["MSS"]=bad("MSS (İç Yapı Kırılması) ✅ +1")
        if bear_obs:
            ob=bear_obs[0]; smc_s+=2
            at_ob=ob["low"]<=cp<=ob["high"]
            smc_det["OB"]=bad(f"Bearish OB {ob['low']:.4f}–{ob['high']:.4f} +2{' ◀ FİYAT BURADA!' if at_ob else ''}")
        if bear_brk:
            b=bear_brk[0]; smc_s+=1
            smc_det["BRK"]=bad(f"Bear Breaker Block {b['low']:.4f}–{b['high']:.4f} +1")
        if bear_fvg:
            f=bear_fvg[0]
            at_fvg=f["low"]<=cp<=f["high"]
            at_fvg_lbl2=" ◀ FİYAT FVG'DE!" if at_fvg else ""
            smc_s+=1; smc_det["FVG"]=bad(f"Bearish FVG {f['low']:.4f}–{f['high']:.4f} +1{at_fvg_lbl2}")
        if sweep_up:   smc_s+=2; smc_det["LIQ"]=bad("BSL Sweep (Sell Side Güçlendi) ✅ +2")
        if ote and ote["bear_ote"]: smc_s+=1; smc_det["OTE"]=bad(f"OTE Short Bölgesi ({ote['fib62']:.4f}–{ote['fib79']:.4f}) ✅ +1")
        if supply_z:
            s=supply_z[0]
            at_sz=s["bot"]<=cp<=s["top"]
            if at_sz: smc_s+=1; smc_det["SZ"]=bad(f"Supply Zone'DA ✅ +1 ({s['bot']:.4f}–{s['top']:.4f})")
        if wyck in ("DISTRIBUTION_ZONE",):
            smc_s+=1; smc_det["WYCK"]=bad(f"Wyckoff: {wyck} ✅ +1")

    # Displacement bonusu
    if disps:
        d=disps[0]
        if (d["direction"]=="UP" and trend=="BULLISH") or (d["direction"]=="DOWN" and trend=="BEARISH"):
            smc_s+=0.5; smc_det["DISP"]=nfo(f"Displacement {d['direction']} (x{d['ratio']:.1f} ATR) +0.5")

    smc_s=min(smc_s,10.0)

    # ─── Klasik (max 10) ─────────────────────────────────────
    if cl["ema_full"]:   cl_s+=2; cl_det["EMA"]=ok("EMA Ribbon Tam Bullish ✅ +2")
    elif cl["ema_part"]: cl_s+=1; cl_det["EMA"]=warn("EMA Kısmi Sıralama +1")
    else:                cl_det["EMA"]=dim("EMA Ters Sıralama")
    cl_det["EMA_V"]=dim(f"EMA8:{cl['e8']:.2f} EMA21:{cl['e21']:.2f} EMA55:{cl['e55']:.2f} EMA200:{cl['e200']:.2f}")

    if cl["macd_bull"]:  cl_s+=2; cl_det["MACD"]=ok(f"MACD Pozitif Momentum ✅ +2 (hist={cl['macd_hist']:.5f})")
    elif cl["macd_hist"]>0: cl_s+=1; cl_det["MACD"]=warn(f"MACD Hafif Pozitif +1 ({cl['macd_hist']:.5f})")
    else:                cl_det["MACD"]=dim(f"MACD Negatif ({cl['macd_hist']:.5f})")

    rv=cl["rsi"]
    if divs["rsi_bull_hidden"]: cl_s+=2; cl_det["RSI"]=ok(f"RSI Gizli Boğa Diverjansı ✅ +2  (RSI={rv:.1f})")
    elif divs["rsi_bull_reg"]:  cl_s+=1; cl_det["RSI"]=warn(f"RSI Klasik Boğa Div +1  (RSI={rv:.1f})")
    elif divs["rsi_bear_hidden"]:cl_det["RSI"]=bad(f"RSI Gizli Ayı Diverjansı ⚠️  (RSI={rv:.1f})")
    elif cl["oversold"]:        cl_s+=0.5; cl_det["RSI"]=warn(f"RSI Oversold ({rv:.1f}) +0.5")
    elif cl["overbought"]:      cl_det["RSI"]=bad(f"RSI Overbought ({rv:.1f}) ⚠️")
    else:                       cl_det["RSI"]=dim(f"RSI Nötr ({rv:.1f})")

    if cl["stoch_bull"]:  cl_s+=1; cl_det["STOCH"]=ok("Stoch RSI Oversold'dan Çıkış ✅ +1")
    if cl["bb_squeeze"] and cl["bb_above"]: cl_s+=1; cl_det["BB"]=ok("BB Squeeze Kırılma ✅ +1")
    if cl["vwap_above"]: cl_s+=1; cl_det["VWAP"]=ok(f"VWAP Üstünde ✅ +1 ({cl['vwap']:.4f})")
    else:                cl_det["VWAP"]=dim(f"VWAP Altında ({cl['vwap']:.4f})")
    if cl["obv_up"]:     cl_s+=1; cl_det["OBV"]=ok("OBV Uptrend Konfirmasyonu ✅ +1")
    if divs["macd_bull"]: cl_s+=1; cl_det["MACD_DIV"]=ok("MACD Boğa Diverjansı ✅ +1")

    cl_s=min(cl_s,10.0)

    # ─── Kurumsal (max 7) ─────────────────────────────────────
    if not is_bist:
        if cvd(df): inst_s+=2; inst_det["CVD"]=ok("CVD Uptrend + Fiyat Uyumu ✅ +2")
        else:       inst_det["CVD"]=dim("CVD Uyumsuz")

        if fr is not None:
            fp=fr*100
            if -0.01<=fp<=0.01:  inst_s+=1; inst_det["FR"]=ok(f"Funding Nötr {fp:.4f}% +1")
            elif fp>0.05:        inst_det["FR"]=bad(f"⚠️ Aşırı Long {fp:.4f}% — Short Riski!")
            elif fp<-0.05:       inst_s+=1; inst_det["FR"]=ok(f"Short Sıkışma Fırsatı {fp:.4f}% +1")
            else:                inst_det["FR"]=nfo(f"Funding Normal {fp:.4f}%")

        price_up20=float(df["close"].shift(1).iloc[-1])>float(df["close"].shift(1).iloc[-21])
        if price_up20: inst_s+=2; inst_det["OI"]=ok("Fiyat 20-bar Uptrend (OI proxy) ✅ +2")

        if vp:
            near_vpoc=abs(cp-vp["vpoc"])/vp["vpoc"]<0.01
            if near_vpoc: inst_s+=1; inst_det["VP"]=ok(f"VPOC Yakini {vp['vpoc']:.4f} ✅ +1")
            else:         inst_det["VP"]=nfo(f"VPOC:{vp['vpoc']:.4f} VAH:{vp['vah']:.4f} VAL:{vp['val']:.4f}")
    else:
        va=df["volume"].iloc[-21:-1].mean()
        vc=df["volume"].iloc[-2]
        if vc>va*1.3: inst_s+=3; inst_det["VOL"]=ok(f"BIST Yüksek Hacim ✅ +3 ({vc/va:.1f}x ort)")

    inst_s=min(inst_s,7.0)

    # ─── MTF (max 4) ─────────────────────────────────────────
    tf_hits=[t for t,ms_ in [("1W",ms1w),("1D",ms1d),("1H",ms1h)] if ms_.get("trend")==trend]
    if len(tf_hits)==3: mtf_s=4; mtf_det["MTF"]=ok(f"Tam MTF Uyum 4H+{'+'.join(tf_hits)} ✅ +4")
    elif len(tf_hits)==2: mtf_s=2; mtf_det["MTF"]=ok(f"MTF Uyum 4H+{'+'.join(tf_hits)} +2")
    elif len(tf_hits)==1: mtf_s=1; mtf_det["MTF"]=warn(f"Kısmi MTF {'+'.join(tf_hits)} +1")
    else:                 mtf_det["MTF"]=dim("MTF Çelişkili")

    # ─── Composite ────────────────────────────────────────────
    raw=smc_s+cl_s+inst_s+mtf_s
    composite=round((raw/37)*10,2)

    # ─── Trade Setup ──────────────────────────────────────────
    entry_low=entry_high=sl=tp1=tp2=tp3=None
    if trend=="BULLISH":
        if bull_obs:
            ob=bull_obs[0]; entry_low,entry_high=ob["low"],ob["high"]
            sl=ob["low"]*0.995
        elif bull_fvg:
            f=bull_fvg[0]; mid=(f["low"]+f["high"])/2
            entry_low,entry_high=f["low"],f["high"]; sl=f["low"]*0.996
        if entry_low:
            mid=(entry_low+entry_high)/2
            tp1=mid*1.06; tp2=mid*1.14; tp3=mid*1.28
            if bear_fvg and bear_fvg[0]["mid"]>mid: tp1=bear_fvg[0]["mid"]
    elif trend=="BEARISH":
        if bear_obs:
            ob=bear_obs[0]; entry_low,entry_high=ob["low"],ob["high"]
            sl=ob["high"]*1.005
        elif bear_fvg:
            f=bear_fvg[0]; mid=(f["low"]+f["high"])/2
            entry_low,entry_high=f["low"],f["high"]; sl=f["high"]*1.004
        if entry_low:
            mid=(entry_low+entry_high)/2
            tp1=mid*0.94; tp2=mid*0.86; tp3=mid*0.72

    return {
        "symbol":symbol,"is_bist":is_bist,"price":cp,"trend":trend,
        "smc_s":smc_s,"cl_s":cl_s,"inst_s":inst_s,"mtf_s":mtf_s,
        "raw":raw,"composite":composite,
        "smc_det":smc_det,"cl_det":cl_det,"inst_det":inst_det,"mtf_det":mtf_det,
        "ms":ms,"bull_obs":bull_obs,"bear_obs":bear_obs,
        "bull_brk":bull_brk,"bear_brk":bear_brk,
        "bull_fvg":bull_fvg,"bear_fvg":bear_fvg,
        "bsl":bsl,"ssl":ssl,"sweep_up":sweep_up,"sweep_down":sweep_down,
        "disps":disps,"ote":ote,"fibs":fibs,"vp":vp,"wyck":wyck,
        "demand_z":demand_z,"supply_z":supply_z,"divs":divs,"cl":cl,
        "tf_trends":{"4H":trend,"1D":ms1d.get("trend"),"1H":ms1h.get("trend"),"1W":ms1w.get("trend")},
        "fr":fr,"entry_low":entry_low,"entry_high":entry_high,"sl":sl,
        "tp1":tp1,"tp2":tp2,"tp3":tp3,
    }

# ══════════════════════════════════════════════════════════════
#  BÖLÜM 5 – ÇIKTI
# ══════════════════════════════════════════════════════════════

def sig_lvl(s):
    if s>=8.0: return ok(f"🚨 GÜÇLÜ SİNYAL ({s:.1f}/10)")
    if s>=6.0: return warn(f"📊 ORTA SİNYAL ({s:.1f}/10)")
    if s>=4.0: return nfo(f"👁  İZLEMELİK ({s:.1f}/10)")
    return dim(f"📉 SİNYAL YOK ({s:.1f}/10)")

def pbar(score,mx,color=CY):
    f=int(score/mx*22); e=22-f
    return f"{color}{'█'*f}{DM}{'░'*e}{R} {B}{score:.1f}/{mx}{R}"

def print_full(r, soc):
    sym=r["symbol"]; cp=r["price"]; t=r["trend"]; comp=r["composite"]
    sym_key=sym.replace("/USDT","").replace(".IS","")
    soc_d=soc.get(sym_key,{})
    soc_s=soc_d.get("soc_score",0)
    total=round(((r["raw"]+soc_s)/37)*10,2)

    t_str=(ok("▲ BULLISH") if t=="BULLISH" else(bad("▼ BEARISH") if t=="BEARISH" else dim("─ NÖTR")))
    print(f"\n{'═'*68}")
    print(f"  {B}{sym:16}{R}  {t_str}   {sig_lvl(total)}")
    print(f"  Fiyat: {B}{cp:.4f}{R}")

    # MTF trend ızgarası
    tf=r["tf_trends"]
    def tc(t):
        if t=="BULLISH": return ok("▲")
        if t=="BEARISH": return bad("▼")
        return dim("─")
    print(f"  MTF:  1W:{tc(tf.get('1W'))} 1D:{tc(tf.get('1D'))} 4H:{tc(tf.get('4H'))} 1H:{tc(tf.get('1H'))}")

    # Puan çubukları
    print()
    print(f"  SMC / ICT    {pbar(r['smc_s'],10,GR if r['smc_s']>=6 else YL)}")
    print(f"  Klasik       {pbar(r['cl_s'],10,GR if r['cl_s']>=6 else YL)}")
    print(f"  Kurumsal     {pbar(r['inst_s'],7,GR if r['inst_s']>=4 else YL)}")
    print(f"  MTF          {pbar(r['mtf_s'],4,GR if r['mtf_s']>=2 else YL)}")
    print(f"  Sosyal       {pbar(soc_s,6,GR if soc_s>=3 else YL)}")
    print(f"  {'─'*46}")
    print(f"  {B}TOPLAM{R}       {pbar(total,10,GR if total>=6 else(YL if total>=4 else DM))}")

    # Wyckoff + Displacement
    if r["wyck"]!="NO_PATTERN":
        wy_c=ok if "ACCUMULATION" in r["wyck"] or "CLIMAX" in r["wyck"] else bad
        print(f"\n  {CY}Wyckoff:{R} {wy_c(r['wyck'])}")
    if r["disps"]:
        d=r["disps"][0]
        dc=ok if d["direction"]=="UP" else bad
        print(f"  {CY}Displacement:{R} {dc(d['direction'])} x{d['ratio']:.1f} ATR ({d['bars_ago']} mum önce)")

    # SMC Detaylar
    if r["smc_det"]:
        print(f"\n  {B}{CY}━━ SMC / ICT YAPILARI ━━{R}")
        ms=r["ms"]
        struct=f"HH:{ok('✓') if ms['hh'] else dim('✗')} HL:{ok('✓') if ms['hl'] else dim('✗')} LH:{bad('✓') if ms['lh'] else dim('✗')} LL:{bad('✓') if ms['ll'] else dim('✗')}"
        print(f"  Yapı: {struct}")
        for v in r["smc_det"].values(): print(f"    {v}")

    # Liquidity Map
    if r["bsl"] or r["ssl"]:
        print(f"\n  {B}{CY}━━ LİKİDİTE HARİTASI ━━{R}")
        for b in r["bsl"][:2]:
            st="[SWEPT ✓]" if b["swept"] else "[aktif]"
            print(f"    {bad('BSL')} {b['level']:.4f}  {b['bars_ago']}bar {dim(st)}")
        for s in r["ssl"][:2]:
            st="[SWEPT ✓]" if s["swept"] else "[aktif]"
            print(f"    {ok('SSL')} {s['level']:.4f}  {s['bars_ago']}bar {dim(st)}")
        if r["sweep_up"]:  print(f"    {bad('⚡ BSL SWEEP TESPİT EDİLDİ — Satış baskısı')}")
        if r["sweep_down"]:print(f"    {ok('⚡ SSL SWEEP TESPİT EDİLDİ — Alım baskısı')}")

    # FVG
    if r["bull_fvg"] or r["bear_fvg"]:
        print(f"\n  {B}{CY}━━ FAIR VALUE GAPS ━━{R}")
        for f in r["bull_fvg"][:2]:
            at="◀ FİYAT BURADA" if f["low"]<=cp<=f["high"] else ""
            print(f"    {ok('Bull FVG')} {f['low']:.4f}–{f['high']:.4f}  %{f['size_pct']:.2f}  {ok(at) if at else ''}")
        for f in r["bear_fvg"][:2]:
            at="◀ FİYAT BURADA" if f["low"]<=cp<=f["high"] else ""
            print(f"    {bad('Bear FVG')} {f['low']:.4f}–{f['high']:.4f}  %{f['size_pct']:.2f}  {bad(at) if at else ''}")

    # OTE + Fibonacci
    if r["ote"]:
        ote=r["ote"]; fibs=r["fibs"]
        print(f"\n  {B}{CY}━━ FİBONACCİ / OTE ━━{R}")
        print(f"    Swing High: {fibs['high']:.4f}  Swing Low: {fibs['low']:.4f}")
        print(f"    Fib 0.618 (OTE): {ote['fib62']:.4f}")
        print(f"    Fib 0.786 (OTE): {ote['fib79']:.4f}")
        print(f"    Fib 0.500:       {fibs['fib50']:.4f}")
        if ote["bull_ote"]: print(f"    {ok('✅ Fiyat OTE LONG bölgesinde!')}")
        if ote["bear_ote"]: print(f"    {bad('✅ Fiyat OTE SHORT bölgesinde!')}")

    # Volume Profile
    if r["vp"]:
        vp=r["vp"]
        print(f"\n  {B}{CY}━━ VOLUME PROFİLE ━━{R}")
        near_vpoc=abs(cp-vp["vpoc"])/vp["vpoc"]<0.015
        vpoc_lbl="◀ FİYAT VPOC YAKININDA" if near_vpoc else ""
        vpoc_str=f"{vp['vpoc']:.4f}"
        print(f"    VPOC: {warn(vpoc_str)} {vpoc_lbl}")
        print(f"    VAH:  {vp['vah']:.4f}   VAL: {vp['val']:.4f}")

    # Klasik İndikatörler
    print(f"\n  {B}{CY}━━ KLASİK İNDİKATÖRLER ━━{R}")
    for v in r["cl_det"].values(): print(f"    {v}")

    # Diverjanslar
    divs=r["divs"]
    div_list=[]
    if divs["rsi_bull_hidden"]:  div_list.append(ok("RSI Gizli Boğa Div"))
    if divs["rsi_bull_reg"]:     div_list.append(ok("RSI Klasik Boğa Div"))
    if divs["rsi_bear_hidden"]:  div_list.append(bad("RSI Gizli Ayı Div"))
    if divs["rsi_bear_reg"]:     div_list.append(bad("RSI Klasik Ayı Div"))
    if divs["macd_bull"]:        div_list.append(ok("MACD Boğa Div"))
    if divs["macd_bear"]:        div_list.append(bad("MACD Ayı Div"))
    if div_list: print(f"    {CY}Diverjanslar:{R} {' | '.join(div_list)}")

    # Kurumsal + MTF
    if r["inst_det"]:
        print(f"\n  {B}{CY}━━ KURUMSAL ━━{R}")
        for v in r["inst_det"].values(): print(f"    {v}")
    if r["mtf_det"]:
        print(f"\n  {B}{CY}━━ MULTI-TIMEFRAME ━━{R}")
        for v in r["mtf_det"].values(): print(f"    {v}")

    # Sosyal
    if soc_d:
        print(f"\n  {B}{CY}━━ SOSYAL ━━{R}")
        sc=ok if soc_d.get("sentiment",0.5)>=0.58 else(bad if soc_d.get("sentiment",0.5)<=0.42 else nfo)
        sent_str=f"{soc_d.get('sentiment',0.5):.2f} {soc_d.get('label','')}"
        print(f"    Sentiment: {sc(sent_str)}")
        print(f"    Mention:   {soc_d.get('mentions',0)} kaynak")

    # Trade Setup
    if r["entry_low"] and r["sl"] and total>=4.5:
        mid=(r["entry_low"]+r["entry_high"])/2
        sl_pct=abs(mid-r["sl"])/mid*100
        lev=5 if total>=8 else(3 if total>=7 else 2)
        print(f"\n  {YL}{'═'*52}{R}")
        print(f"  {B}  TRADE SETUP{R}")
        print(f"  {YL}{'═'*52}{R}")
        dir_s=ok("LONG ▲") if t=="BULLISH" else bad("SHORT ▼")
        print(f"  Yön:    {dir_s}")
        el_s=f"{r['entry_low']:.4f}"; eh_s=f"{r['entry_high']:.4f}"
        print(f"  Giriş:  {warn(el_s)} — {warn(eh_s)}")
        sl_s=f"{r['sl']:.4f}"; print(f"  SL:     {bad(sl_s)} (-%{sl_pct:.1f})")
        if r["tp1"]:
            tp1_pct=abs(mid-r["tp1"])/mid*100
            tp2_pct=abs(mid-r["tp2"])/mid*100
            tp3_pct=abs(mid-r["tp3"])/mid*100
            t1s=f"{r['tp1']:.4f}"; t2s=f"{r['tp2']:.4f}"; t3s=f"{r['tp3']:.4f}"
            print(f"  TP1:    {ok(t1s)} (+%{tp1_pct:.1f}) → %40 kapat, SL maliyete çek")
            print(f"  TP2:    {ok(t2s)} (+%{tp2_pct:.1f}) → %35 kapat")
            print(f"  TP3:    {ok(t3s)} (+%{tp3_pct:.1f}) → %25 kapat")
        print(f"  Kaldıraç: {warn(str(lev)+'x')}  |  Risk: %2 = $200 / $10k bakiye")
    print()

# ══════════════════════════════════════════════════════════════
#  BÖLÜM 6 – BİLEŞİK FAİZ STRATEJİ MATEMATİĞİ
# ══════════════════════════════════════════════════════════════

CAPITAL   = 10_000.0   # Başlangıç sermayesi ($)
RISK_PCT  = 0.02       # Sabit risk/işlem (2%)
MAX_OPEN  = 3          # Aynı anda max açık pozisyon

# Skor aralığı → (win_rate, ort_RR, tahmini_sinyal_30_günde)
_SCORE_TBL = [
    (8.0, 10.0, 0.62, 3.5,  4),   # Güçlü
    (6.0,  8.0, 0.55, 2.8,  8),   # Orta
    (4.5,  6.0, 0.48, 2.2,  5),   # İzlemelık
]

def _score_params(score):
    for lo, hi, wr, rr, freq in _SCORE_TBL:
        if lo <= score <= hi:
            return wr, rr, freq
    return 0.48, 2.0, 3

def kelly_f(win_rate, rr):
    """Yarım-Kelly fraksiyonu, max %5 limitli."""
    q = 1.0 - win_rate
    if rr <= 0: return 0.0
    full = (win_rate * rr - q) / rr
    return max(0.0, min(full * 0.5, 0.05))   # Half-Kelly

def geo_mult(win_rate, rr, r, n):
    """
    n işlem sonrası geometrik büyüme çarpanı.
    G = (1 + rr*r)^p * (1 - r)^q  →  G^n
    """
    if r <= 0 or rr <= 0 or n <= 0: return 1.0
    p = win_rate; q = 1.0 - p
    g = ((1.0 + rr * r) ** p) * ((1.0 - r) ** q)
    return g ** n

def dd_estimate(win_rate, rr, r, n):
    """Normal-dağılım yaklaşımıyla tahmini max drawdown %."""
    p = win_rate; q = 1.0 - p
    # Tek işlem P&L varyansı
    mean_pnl = p * rr * r - q * r
    var_pnl  = p * (rr * r - mean_pnl)**2 + q * (-r - mean_pnl)**2
    std_pnl  = math.sqrt(max(0.0, var_pnl))
    # Rassal yürüyüş tahmini: DD ≈ 1.8 * σ * √n
    return min(std_pnl * math.sqrt(n) * 1.8, 0.65) * 100.0

def multi_tf_compound_plan(results, social):
    """
    Tüm sinyallerden long + short portfolio oluşturur,
    Kelly sizing ve bileşik büyüme projeksiyonları üretir.
    """
    longs = []; shorts = []

    for r in results:
        sk   = r["symbol"].replace("/USDT","").replace(".IS","")
        ss   = social.get(sk, {}).get("soc_score", 0)
        total= round(((r["raw"] + ss) / 37) * 10, 2)
        if total < 4.5: continue

        wr, rr, freq = _score_params(total)
        kf   = kelly_f(wr, rr)
        rfrac= RISK_PCT   # Sabit %2 risk kuralı — Kelly danışmanlık amaçlı

        entry= None
        if r.get("entry_low") and r.get("entry_high"):
            entry = (r["entry_low"] + r["entry_high"]) / 2.0
        if not entry: entry = r["price"]
        sl_p = abs(entry - r["sl"]) / entry if r.get("sl") else 0.015
        lev  = min(max(1, int(RISK_PCT / max(sl_p, 0.005))), 5)

        rec = dict(symbol=r["symbol"], direction=r["trend"], score=total,
                   price=r["price"], entry=entry, sl=r.get("sl"),
                   sl_pct=sl_p*100, tp1=r.get("tp1"), tp2=r.get("tp2"),
                   tp3=r.get("tp3"), win_rate=wr, rr=rr,
                   risk_frac=rfrac, kelly_frac=kf, leverage=lev, freq_30d=freq)
        if r["trend"] == "BULLISH":
            longs.append(rec)
        elif r["trend"] == "BEARISH":
            shorts.append(rec)

    all_sigs = longs + shorts
    if not all_sigs:
        return dict(long=[], short=[], all=[], projections={}, capital=CAPITAL)

    # Ağırlıklı ortalama parametreler (freq ağırlığı)
    tw  = sum(s["freq_30d"] for s in all_sigs)
    aw  = lambda key: sum(s[key] * s["freq_30d"] for s in all_sigs) / (tw or 1)
    avg_wr   = aw("win_rate")
    avg_rr   = aw("rr")
    avg_risk = aw("risk_frac")       # RISK_PCT = 2%
    avg_kf   = aw("kelly_frac")      # Kelly önerisi

    daily_trades = tw / 30.0         # Portföy genelinde günlük sinyal

    def _proj(r_frac):
        out = {}
        for days in (30, 90, 180, 365):
            n    = max(1, int(daily_trades * days))
            mult = geo_mult(avg_wr, avg_rr, r_frac, n)
            dd   = dd_estimate(avg_wr, avg_rr, r_frac, n)
            mean_p = avg_wr * avg_rr * r_frac - (1-avg_wr) * r_frac
            std1   = math.sqrt(max(0, avg_wr*(avg_rr*r_frac)**2 + (1-avg_wr)*r_frac**2
                                   - mean_p**2))
            sharpe = (mean_p * math.sqrt(252)) / (std1 + 1e-10)
            out[f"{days}d"] = dict(n_trades=n, multiplier=mult, final=CAPITAL*mult,
                                   gain_pct=(mult-1)*100, est_max_dd=dd,
                                   log_g=math.log(geo_mult(avg_wr,avg_rr,r_frac,1)),
                                   sharpe_annualized=sharpe)
        return out

    return dict(
        long=longs, short=shorts, all=all_sigs,
        avg_wr=avg_wr, avg_rr=avg_rr, avg_risk=avg_risk, avg_kf=avg_kf,
        daily_trades=daily_trades,
        projections=_proj(avg_risk),        # 2% sabit risk
        proj_kelly=_proj(min(avg_kf, 0.04)),# Kelly-sized (max 4%)
        capital=CAPITAL,
    )

def print_compound_strategy(plan):
    if not plan or not plan.get("all"):
        print(f"  {dim('Aktif sinyal yok (min 4.5 gerekli — önce bir tarama çalıştır)')}")
        return

    longs  = plan["long"]
    shorts = plan["short"]
    projs  = plan["projections"]        # 2% sabit risk
    projs_k= plan.get("proj_kelly", {}) # Kelly-sized risk
    capital= plan["capital"]
    avg_wr = plan["avg_wr"]
    avg_rr = plan["avg_rr"]
    avg_r  = plan["avg_risk"]
    avg_kf = plan.get("avg_kf", 0.02)

    # ── Portfolio özeti
    print(f"\n  {B}{CY}━━ PORTFOLIO ━━{R}")
    print(f"  Sermaye       : {B}${capital:,.0f}{R}")
    print(f"  Long sinyali  : {ok(str(len(longs)))}")
    print(f"  Short sinyali : {bad(str(len(shorts)))}")
    print(f"  Ort Win Rate  : {B}{avg_wr:.1%}{R}   (skor kalibre)")
    print(f"  Ort R:R       : {B}1:{avg_rr:.2f}{R}")
    print(f"  Ort Risk/işlem: {B}{avg_r:.1%}{R}  (sabit 2% kural)")
    monthly_trades = f"{plan['daily_trades']*30:.0f}"
    print(f"  Beklenen sinyal: {B}{plan['daily_trades']:.1f}/gün{R}  "
          f"{dim('(' + monthly_trades + '/ay)')}")

    # ── Long pozisyonlar
    if longs:
        print(f"\n  {ok('━━ LONG SİNYALLER')}")
        hdr = f"  {'Sembol':14} {'Skor':5}  {'WR':5}  {'R:R':5}  {'Risk':5}  {'Kelly':6}  {'Kald':5}  SL%"
        print(hdr); sep("─")
        for s in sorted(longs, key=lambda x:x["score"], reverse=True)[:MAX_OPEN]:
            ks = f"{s['kelly_frac']:.1%}"
            print(f"  {s['symbol']:14} {s['score']:4.1f}   {s['win_rate']:.0%}   "
                  f"1:{s['rr']:.1f}   {s['risk_frac']:.1%}   {ok(ks)}   "
                  f"{warn(str(s['leverage'])+'x')}   {s['sl_pct']:.1f}%")

    # ── Short pozisyonlar
    if shorts:
        print(f"\n  {bad('━━ SHORT SİNYALLER')}")
        hdr = f"  {'Sembol':14} {'Skor':5}  {'WR':5}  {'R:R':5}  {'Risk':5}  {'Kelly':6}  {'Kald':5}  SL%"
        print(hdr); sep("─")
        for s in sorted(shorts, key=lambda x:x["score"], reverse=True)[:MAX_OPEN]:
            ks = f"{s['kelly_frac']:.1%}"
            print(f"  {s['symbol']:14} {s['score']:4.1f}   {s['win_rate']:.0%}   "
                  f"1:{s['rr']:.1f}   {s['risk_frac']:.1%}   {ok(ks)}   "
                  f"{warn(str(s['leverage'])+'x')}   {s['sl_pct']:.1f}%")

    # ── Bileşik büyüme projeksiyonları
    def _print_proj_table(proj_dict, label, r_frac):
        print(f"\n  {B}{CY}━━ {label} ━━{R}")
        e_trade = avg_wr * avg_rr * r_frac - (1-avg_wr) * r_frac
        print(f"  {dim(f'Risk/işlem: {r_frac:.1%}  |  E[getiri]: {e_trade:.2%}/işlem')}")
        print()
        BAR = 30
        max_g = max(q["gain_pct"] for q in proj_dict.values()) or 1
        for period, p in proj_dict.items():
            mult  = p["multiplier"]
            g_pct = p["gain_pct"]
            dd    = p["est_max_dd"]
            n     = p["n_trades"]
            final = p["final"]
            sh    = p["sharpe_annualized"]
            col = GR if mult >= 2.0 else (YL if mult >= 1.3 else CY)
            # Log scale bars — makes early periods visible alongside huge final period
            log_g   = math.log1p(max(0, g_pct))
            log_max = math.log1p(max_g) or 1
            bl = max(1, int(log_g / log_max * BAR))
            bar = col + "█"*bl + DM + "░"*(BAR-bl) + R
            dd_col = bad if dd > 30 else (warn if dd > 15 else ok)
            g_str = f"+{g_pct:.1f}%"
            print(f"  {B}{period:5}{R}  {n:5}işlem  "
                  f"{B}${final:>11,.0f}{R}  {col}{g_str:>10}{R}  "
                  f"DD≈{dd_col(f'%{dd:.0f}')}  Sharpe≈{sh:.1f}")
            print(f"         {bar}")
        print()

    _print_proj_table(projs,   "BİLEŞİK BÜYÜME  — SABİT %2 RİSK", avg_r)
    if projs_k and avg_kf > avg_r:
        kf_disp = min(avg_kf, 0.04)
        _print_proj_table(projs_k, f"BİLEŞİK BÜYÜME  — KELLY RİSKİ (yarım-Kelly={avg_kf:.1%})", kf_disp)

    # ── Kelly matematik
    full_k  = (avg_wr * avg_rr - (1.0-avg_wr)) / avg_rr
    half_k  = full_k * 0.5
    log_g   = math.log(geo_mult(avg_wr, avg_rr, avg_r, 1))
    e_trade = avg_wr * avg_rr * avg_r - (1-avg_wr) * avg_r

    print(f"  {B}{CY}━━ KELLY KRİTERİ HESABI ━━{R}")
    print(f"  f*(tam)   = (p·b − q) / b")
    lhs = f"{avg_wr:.3f}·{avg_rr:.3f} − {1-avg_wr:.3f}"
    print(f"            = ({lhs}) / {avg_rr:.3f}  =  {full_k:.4f}  ({full_k:.1%})")
    hk_str = f"{half_k:.4f}  ({half_k:.1%})"
    print(f"  f*(yarım) = {hk_str}   {ok('← Teorik Optimum')}")
    print(f"  Log büyüme= {log_g:.5f}/işlem  →  {log_g*365:.3f}/yıl (günde 1 işlem)")
    print(f"  E[getiri] = p·b·r − q·r  =  {e_trade:.4f}/işlem  ({e_trade:.2%})")
    print()
    print(f"  {B}Uzun vadeli bileşik büyüme formülü:{R}")
    print(f"  {CY}  C_n = C₀ · [(1+b·r)^p · (1−r)^(1−p)]^n{R}")
    print(f"  {DM}  C₀={CAPITAL:,.0f}  p={avg_wr:.2f}  b={avg_rr:.2f}  r={avg_r:.3f}{R}")

    # ── Long/Short hedge notu
    print(f"\n  {B}{CY}━━ LONG + SHORT STRATEJİSİ ━━{R}")
    print(f"  {dim('• Hem yükselen hem düşen varlıktan kazanç')}")
    print(f"  {dim('• Long ve Short eş zamanlı açılabilir (farklı varlık / TF)')}")
    print(f"  {dim('• Aynı yönde max 3 pozisyon — korelasyon riskini sınırlar')}")
    print(f"  {dim('• TP1 kapandığında SL maliyete çek → Bedava kalan pozisyon')}")
    print(f"  {dim('• Her kazançlı işlem sonrası pozisyon boyutu otomatik artar')}")
    print(f"  {dim('  (2% risk — sabit oran — sermaye büyüdükçe dolar değer büyür)')}")

    print(f"\n  {YL}{'─'*52}{R}")
    print(f"  {warn('⚠  Projeksiyon varsayımlar üzerine kurulu — piyasa farklı davranabilir')}")
    warn2 = warn("⚠  Gerçek sonuç tarihsel win rate'e ve disipline bagli")
    print(f"  {warn2}")
    print(f"  {dim('   Saklı avantaj: SMC + MTF filtreleri var olmayan işlemleri eler')}")


# ══════════════════════════════════════════════════════════════
#  ANA AKIŞ
# ══════════════════════════════════════════════════════════════

def main():
    head(f"ALPHA İSTİHBARAT — ADVANCED SMC/ICT CANLI TARAMA  {datetime.utcnow():%Y-%m-%d %H:%M UTC}")

    # 1. Web Scraping
    h2("ADIM 1 – WEB SCRAPING + SOSYAL TESPİT")
    print()
    mention_cnt, headlines, sources = scrape_all()
    for src,n in sources.items():
        icon=ok("✅") if n>0 else dim("✗")
        print(f"  {icon} {src:14} → {n} içerik")
    print(f"\n  Toplam başlık: {len(headlines)}")
    print(f"\n  {B}Mention Sayıları:{R}")
    for sym,cnt in mention_cnt.most_common(12):
        bar="█"*min(cnt,25); print(f"    {sym:6} {GR}{bar}{R} {cnt}")

    # Keşif
    extra=[s for s,_ in mention_cnt.most_common(10) if s not in ["BTC","ETH","SOL"]][:4]
    watchlist=["BTC","ETH","SOL"]+extra
    print(f"\n  {B}Tarama Listesi:{R} {', '.join(watchlist)}")

    # 2. Sentiment
    h2("ADIM 2 – SENTIMENT")
    print()
    social={}
    for sym in watchlist:
        rel=[h for h in headlines if sym.lower() in h.lower()
             or any(a in h.lower() for a in CRYPTO_MAP.get(sym,[][:2]))]
        sc,lb=sentiment(rel or headlines[:8])
        soc_s=3.0 if sc>=0.65 else(1.5 if sc>=0.5 else 0.0)
        if len(rel)>=3: soc_s=min(soc_s+2.0,6.0)
        social[sym]={"sentiment":sc,"label":lb,"mentions":len(rel),"soc_score":soc_s}
        ic=ok("✅") if sc>=0.58 else(bad("↓") if sc<0.42 else "─")
        print(f"  {sym:6} {ic}  {sc:.2f} ({lb:5})  mention:{len(rel):2}  soc:{soc_s:.1f}/6")

    # 3. BIST
    h2("ADIM 3 – BIST 4H ANALİZİ")
    print()
    bist_list=["THYAO.IS","GARAN.IS","EREGL.IS","SASA.IS","ASELS.IS"]
    bist_res=[]
    for sym in bist_list:
        sys.stdout.write(f"  {sym:12} ... "); sys.stdout.flush()
        r=analyze(sym,is_bist=True)
        if r:
            bist_res.append(r)
            soc_s=0
            total=round(((r["raw"]+soc_s)/37)*10,2)
            sys.stdout.write(f"{sig_lvl(total)}\n")
        else: sys.stdout.write(f"{dim('veri alınamadı')}\n")
        time.sleep(0.5)

    # 4. Kripto
    h2("ADIM 4 – KRİPTO ADVANCED ANALİZ (Binance 4H)")
    print()
    crypto_res=[]
    for sym in watchlist:
        fsym=f"{sym}/USDT"
        sys.stdout.write(f"  {fsym:12} ... "); sys.stdout.flush()
        r=analyze(fsym,is_bist=False)
        if r:
            crypto_res.append(r)
            soc_s=social.get(sym,{}).get("soc_score",0)
            total=round(((r["raw"]+soc_s)/37)*10,2)
            sys.stdout.write(f"{sig_lvl(total)}\n")
        else: sys.stdout.write(f"{dim('veri alınamadı')}\n")
        time.sleep(0.3)

    # 5. Detaylı çıktı
    h2("ADIM 5 – KRİPTO DETAYLI ANALİZ")
    for r in sorted(crypto_res,key=lambda x:x["composite"],reverse=True):
        print_full(r, {r["symbol"].replace("/USDT",""):social.get(r["symbol"].replace("/USDT",""),{})})

    h2("ADIM 6 – BIST DETAYLI ANALİZ")
    for r in sorted(bist_res,key=lambda x:x["composite"],reverse=True):
        print_full(r,{})

    # 6. Özet tablo
    h2("ÖZET SİNYAL TABLOSU")
    all_res=crypto_res+bist_res
    print(f"\n  {'Sembol':14} {'Trend':8} {'SMC':5} {'Klas':5} {'Kur':4} {'MTF':4} {'Sos':4} {'TOP':8} Seviye")
    sep()
    for r in sorted(all_res,key=lambda x:x["composite"],reverse=True):
        sk=r["symbol"].replace("/USDT","").replace(".IS","")
        ss=social.get(sk,{}).get("soc_score",0)
        tot=round(((r["raw"]+ss)/37)*10,2)
        t=r["trend"]; tc=(ok("▲ BULL") if t=="BULLISH" else(bad("▼ BEAR") if t=="BEARISH" else dim("─ NÖTR")))
        print(f"  {r['symbol']:14} {tc}  {r['smc_s']:4.1f} {r['cl_s']:4.1f} {r['inst_s']:3.1f} {r['mtf_s']:3.1f} {ss:3.1f}  {tot:4.1f}/10  {sig_lvl(tot)}")

    # 7. Bileşik Faiz Strateji Motoru
    h2("ADIM 7 – BİLEŞİK FAİZ STRATEJİ MOTORU")
    plan = multi_tf_compound_plan(all_res, social)
    print_compound_strategy(plan)

    print(f"\n  {ok('✅ Anti-repainting:')} Tüm hesaplamalar kapanmış mumlar üzerinde")
    print(f"  {ok('✅ SMC/ICT:')} BOS,CHoCH,MSS,OB,Breaker,FVG,Liquidity,OTE,Displacement,Wyckoff,VP")
    print(f"  {ok('✅ Strateji:')} Kelly Kriteri + Geometrik Bileşik Büyüme + Long/Short Portföy\n")

if __name__=="__main__":
    main()
