"""_engine_path.py — Botlar/ klasöründeki tüm botların ortak kurulum modülü.
Repo-göreli yol kurar (taşınabilir), compound_engine'i import eder, veri yolunu ayarlar.
Böylece 'buradan çekince çalışır' — uyg/src ve bot/engine/data_v31 repo içinde olduğu sürece."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))          # .../trade
SRC  = os.path.join(REPO, "uyg", "src")
DATA = os.path.join(REPO, "bot", "engine", "data_v31")          # 1H OHLCV top5

sys.path.insert(0, SRC)
import compound_engine as E                                      # doğrulanmış baz motor
E.DATA_DIR = DATA                                                # repo-göreli veri
CACHE = "/tmp/botlar_sigs.pkl"

def prepare():
    """Sinyalleri kur + walk-forward discriminator eğit (ilk çağrı birkaç dk, sonra cache)."""
    rows = E.build_signals(cache=CACHE)
    P = E.walk_forward_proba(rows)
    return rows, P

def report(name, r, risk_note):
    print("="*70)
    print(f"  {name}")
    print("="*70)
    print(f"  $250 → ${r['eq']:.0f}   |   CAGR %{r['cagr']:.1f}   |   MaxDD %{r['mdd']:.1f}   |   WR %{r['wr']:.0f}   |   {r['n']} işlem")
    print(f"  Risk profili: {risk_note}")
    print(f"  ⚠️ BACKTEST (OOS 2024-26 walk-forward). DSR%31 → edge istatistiksel kesin değil.")
    print(f"     Gerçek parada önce PAPER-TRADE. Kaldıraç = dayanabileceğin MaxDD.")
