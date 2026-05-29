"""
data_gen.py
===========
Gerçekçi saatlik OHLCV üretici.

NEDEN SENTETİK VERİ?
  Bu ortamın ağ politikası tüm kripto borsalarını (Binance, Bybit, OKX,
  Kraken, Coinbase, KuCoin) ve Yahoo Finance'i engelliyor (403). Dolayısıyla
  canlı ETH verisi çekilemiyor.

  Aslında look-ahead (geleceği görme) hatasını KANITLAMAK için sentetik veri
  DAHA güçlü bir araçtır: Veriyi biz ürettiğimiz için, içinde sömürülebilir
  hiçbir 'gerçek' edge OLMADIĞINI kesin biliyoruz. Eğer botun backtest'i bu
  veride yine de %90 kazanma oranı ve 780x getiri üretiyorsa, bu sonuç
  %100 metodoloji artefaktıdır — piyasa edge'i değil.

  Üretim: Geometrik Brownian Motion (GBM). Her saatlik mum, 60 dakikalık
  alt-adımdan oluşturulur → gerçekçi gövde + fitil (high/low) yapısı.
  ETH benzeri parametreler: yıllık vol ~%70, çeşitli rejimler.
"""
import numpy as np
import pandas as pd

HOURS_PER_YEAR = 24 * 365


def gen_ohlcv(n_bars=8760, mu_annual=0.0, sigma_annual=0.70,
              start_price=3000.0, seed=0, sub=60):
    """
    GBM ile saatlik OHLCV. mu_annual=drift, sigma_annual=yıllık volatilite.
    sub = saat başına alt-adım (intrabar high/low için).
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / (HOURS_PER_YEAR * sub)
    mu = mu_annual; sig = sigma_annual

    total_steps = n_bars * sub
    drift = (mu - 0.5 * sig ** 2) * dt
    shock = sig * np.sqrt(dt) * rng.standard_normal(total_steps)
    log_path = np.log(start_price) + np.cumsum(drift + shock)
    price = np.exp(log_path).reshape(n_bars, sub)

    o = price[:, 0]
    c = price[:, -1]
    h = price.max(axis=1)
    l = price.min(axis=1)
    # Hacim: fiyat hareketiyle hafif korele, log-normal taban
    ret = np.abs(np.diff(np.log(c), prepend=np.log(c[0])))
    vol = (1.0 + 8.0 * ret) * np.exp(rng.normal(0, 0.3, n_bars)) * 1000.0

    idx = pd.date_range("2025-05-29", periods=n_bars, freq="1h")
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": vol},
                      index=idx)
    return df


def regime(name, seed):
    """İsimli rejimler — adil test için boğa/ayı/yatay/gerçekçi karışık."""
    if name == "bull":      # güçlü yükseliş trendi
        return gen_ohlcv(mu_annual=1.20, sigma_annual=0.65, seed=seed)
    if name == "bear":      # düşüş trendi
        return gen_ohlcv(mu_annual=-0.60, sigma_annual=0.75, seed=seed)
    if name == "chop":      # yatay / belirsiz
        return gen_ohlcv(mu_annual=0.0, sigma_annual=0.55, seed=seed)
    if name == "realistic": # hafif pozitif drift, yüksek vol (ETH benzeri)
        return gen_ohlcv(mu_annual=0.25, sigma_annual=0.80, seed=seed)
    raise ValueError(name)


if __name__ == "__main__":
    for rg in ["bull", "bear", "chop", "realistic"]:
        df = regime(rg, seed=42)
        tot = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
        print(f"{rg:10s}  bars={len(df)}  "
              f"fiyat ${df['close'].iloc[0]:.0f}->${df['close'].iloc[-1]:.0f} "
              f"({tot:+.0f}%)  vol_yillik~{df['close'].pct_change().std()*np.sqrt(8760)*100:.0f}%")
