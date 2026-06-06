# AGENT.md — 02_combo

**Ne:** Kripto trend Top-3 + funding-pozisyonlama, inverse-vol. `01_xasset`'in kripto-only
çekirdeği / offline yedeği. Kanonik: `uyg/Botlar/bot_combo.py`.

**Durum:** OOS Sharpe 1.74 (WF-opt 2.25), MaxDD −14%. DSR 0.99/PBO 0.03 geçti. Paper adayı.

**YAP:** WF parametre optimizasyonu kombo'yu 2.25'e çıkarır (run_wfopt.py); ABD kolu ekleyince
01_xasset olur (üstün). **YAPMA:** ML sinyal-gate (zarar); funding kolunu WF-optimize etme
(overfit, 1.31→0.24 — sabit default'ta bırak). Kanıt: `quantlab/reports_out/{combo,wfopt}.md`.
