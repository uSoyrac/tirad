import os
import subprocess
import time

BOTS = [
    "bot_kararli.py",
    "bot_dengeli.py",
    "bot_optimal.py",
    "bot_quantpro.py",
    "bot_rejim.py"
]

TIMEFRAMES = {
    "4H": "/Users/uygar/trade/uyg/src/mktdata_forex_4h",
    "1D": "/Users/uygar/trade/uyg/src/mktdata_forex_1d"
}

# Delete cache before running to force rebuild for new dataset
def clear_cache():
    if os.path.exists("/tmp/compound_sigs.pkl"):
        os.remove("/tmp/compound_sigs.pkl")

print("=" * 80)
print("FOREX TOP 5 BOT BACKTEST SUITE")
print("Pairs: EURUSD, GBPUSD, USDJPY, AUDUSD")
print("=" * 80)

results = []

for tf_name, data_dir in TIMEFRAMES.items():
    print(f"\n\n{'='*30} RUNNING ON {tf_name} TIMEFRAME {'='*30}")
    
    # Common environment variables for Forex
    env = os.environ.copy()
    env["DATA_DIR"] = data_dir
    env["COINS"] = "EURUSD=X,GBPUSD=X,USDJPY=X,AUDUSD=X"
    env["FILE_SFX"] = ".csv"
    env["TP"] = "0.005"   # 0.5%
    env["SL"] = "0.0025"  # 0.25%
    env["COST"] = "0.00015" # 0.015% round trip (typical forex spread/comms)
    env["REGIME_DATA"] = f"{data_dir}/EURUSD=X.csv"

    for bot in BOTS:
        print(f"\n>>> Executing {bot} on {tf_name} ...")
        clear_cache()
        try:
            start = time.time()
            res = subprocess.run(
                ["python3", bot],
                env=env,
                cwd="/Users/uygar/trade/uyg/Botlar",
                capture_output=True,
                text=True
            )
            print(res.stdout)
            if res.stderr:
                print(f"Warnings/Errors:\n{res.stderr}")
            print(f"Finished in {time.time() - start:.1f}s")
        except Exception as e:
            print(f"Failed to run {bot}: {e}")
