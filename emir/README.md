# emir/ — Gerçek Veri Çalışma Alanı (GitHub Actions üzerinden)

Bu konteynerin (Claude'un çalıştığı ortam) interneti kapalı (allowlist). Bu yüzden
gerçek borsa verisini **GitHub Actions runner'ında** çekiyoruz — orada gerçek
internet var.

## Akış
1. `emir/fetch_and_backtest.py` push edilince `.github/workflows/emir-backtest.yml`
   otomatik tetiklenir.
2. CI; Binance → Bybit → OKX sırasıyla **anahtarsız** public veri çeker
   (son 3 ay, 4H, BTC/ETH/SOL/BNB/XRP).
3. Repodaki gerçek strateji (`uyg/src/real_backtest_3m.py`) ve gerçek ORP motoru
   (`uyg/src/dynamic_optimizer.py`) ile backtest + $100 testi yapılır.
4. Sonuçlar `emir/results_real.md` dosyasına yazılıp **repoya geri commit** edilir
   (`[skip ci]` ile sonsuz döngü engellenir).

## Elle tetikleme
GitHub → Actions → "Emir Real Backtest" → Run workflow (ay sayısı seçilebilir).

## Not
Strateji, AGENT.md kurallarının temiz/bağımsız uygulamasıdır; tam `score_slice_v2`
motorunun birebir kopyası değildir. Sayılar gerçek veriden ve gerçek komisyondan gelir.
