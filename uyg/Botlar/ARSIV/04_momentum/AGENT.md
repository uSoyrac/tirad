# AGENT.md — 04_momentum

**Ne:** 20 coin cross-sectional Top-3 momentum (60-bar ROC), ATR-stop. Kanonik:
`uyg/Botlar/bot_xsec_momentum.py`.

**Durum:** OOS Sharpe 1.12 (WF-opt 1.86), win %41.8 (+$70/işlem), MaxDD −30%. Paper adayı.

**Not:** En yüksek win-rate'li +EV strateji ama tek-kol drawdown yüksek + random alt-evrende
kırılgan (medyan 0.06). **YAP:** WF-optimize (ROC30/top-1 → 1.86); xasset/combo'da kol olarak
kullan. **YAPMA:** tek başına büyük sermaye (MaxDD −30%). Kanıt: `quantlab/reports_out/{bakeoff,xsection,robustness,botopt}.md`.
