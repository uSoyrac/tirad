# TIRAD AI - The Algorithmic Blackjack Bot

Tirad AI is a crypto algorithmic trading bot built on the philosophy of "Blackjack Card Counting." Instead of predicting the market, it calculates mathematical probabilities and applies an exponential compounding engine (Optimized Recovery Progression - ORP) only when the statistical edge is in our favor.

## 🏆 Version History & Backtest Results (2-Year Data)

The following table summarizes the evolution of our most powerful setups against 24 months of real Binance 4H data, accounting for actual Maker fees and zero look-ahead bias.

| Versiyon / Özellik | V18 Ultimate (Agresif Büyüme) | V19 Champion (Dengeli Güvenlik) | V20 AI (Kusursuz Keskin Nişancı) |
| :--- | :--- | :--- | :--- |
| **Filtre Mantığı** | Statik (Hacim < 2.5x) | Statik (Hacim < 2.0x) | Makine Öğrenmesi (XGBoost > 0.48) |
| **Toplam İşlem (2 Yıl)**| 836 İşlem | 750 İşlem | **98 İşlem** |
| **Win Rate** | %44.9 | %45.5 | **%91.6** 🔥 |
| **Kasanın Gördüğü Dip**| $5.93 (İflasın eşiği) | $6.80 | **$100.00** (SIFIR DRAWDOWN) 🛡️ |
| **Nihai Net Kâr** | **$316 Milyon** 🥇 | $118 Milyon | $14.6 Milyon |

- **V18 Ultimate:** Maximizes compounding by taking more trades. Most profitable but requires surviving deep drawdowns.
- **V19 Champion:** Filters out volume spikes (Whale Traps) to slightly increase win rate and safety, but loses some compounding speed.
- **V20 XGBoost AI:** The Holy Grail. Uses Supervised Machine Learning to achieve a 91.6% Win Rate. Zero drawdown, but much slower compounding due to extreme selectivity.

## Project Structure
- `/src/v19_live_bot.py`: The live execution engine for Binance API.
- `/src/versions/`: Historical backtest scripts and grid search algorithms.
- `/docs/`: Detailed markdown reports of every major backtest run.
