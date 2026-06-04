"""Single source of truth for all run configuration.

Everything that influences a backtest result lives here as a validated pydantic
model. No magic numbers scattered in the code: if it changes behaviour, it is a
config field. This is what makes a run reproducible and auditable.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class DataConfig(BaseModel):
    exchange: str = "binance"
    symbol: str = "BTC/USDT"
    market_type: Literal["spot", "perp"] = "spot"
    # Primary (trading) timeframe MUST be first; later entries are higher TFs.
    timeframes: list[str] = ["4h", "1d"]
    start: date = date(2021, 1, 1)
    end: date = date(2026, 5, 31)
    cache_dir: Path = Path("data_cache")
    # Optional CSV to seed the parquet cache offline (schema: ts,open,high,low,close,volume).
    seed_csv: Path | None = None

    @property
    def primary_tf(self) -> str:
        return self.timeframes[0]


class CostConfig(BaseModel):
    """Realistic frictions. A backtest without these is fiction."""

    taker_fee: float = 0.0004  # 0.04% per side
    maker_fee: float = 0.0002
    slippage_bps: float = 5.0  # 0.05% adverse fill, applied to every fill
    funding_enabled: bool = False  # perp only
    funding_mode: Literal["flat", "historical"] = "flat"
    flat_funding_rate: float = 0.0001  # per funding interval, paid by longs when positive
    funding_interval_hours: int = 8


class RiskConfig(BaseModel):
    """Fixed-fractional ONLY. No martingale, by design (see CLAUDE.md)."""

    bankroll: float = 10_000.0
    risk_per_trade: float = 0.01  # fraction of equity risked to the stop
    max_leverage: float = 3.0
    stop_atr_mult: float = 1.5
    tp_atr_mult: float | None = 3.5  # None => let the stop / signal exit handle it
    atr_period: int = 14
    # Stop/TP geometry: "atr" (ATR-multiple, default) or "pct" (fixed % of entry,
    # for asymmetric 'sniper' R/R like TP +10% / SL -2%).
    stop_mode: Literal["atr", "pct"] = "atr"
    stop_pct: float = 0.02
    tp_pct: float | None = 0.10
    daily_dd_killswitch: float = 0.06  # flatten + pause for the day if breached
    total_dd_killswitch: float = 0.25  # flatten + halt the run if breached

    @model_validator(mode="after")
    def _sane(self) -> RiskConfig:
        if not 0 < self.risk_per_trade < 1:
            raise ValueError("risk_per_trade must be in (0, 1)")
        if self.max_leverage < 1:
            raise ValueError("max_leverage must be >= 1")
        return self


class SplitConfig(BaseModel):
    """Train (in-sample) vs out-of-sample. The OOS window is sacred."""

    train_end: date = date(2024, 12, 31)  # bars <= this are in-sample
    walk_forward: bool = True
    train_months: int = 24
    test_months: int = 6
    step_months: int = 6


class AgentSpec(BaseModel):
    """One signal agent in the ensemble. Params are passed verbatim to its score fn."""

    name: Literal["supertrend", "macd", "donchian"]
    weight: float = 1.0
    params: dict[str, float] = Field(default_factory=dict)


class EnsembleConfig(BaseModel):
    """Weighted signal ensemble. Net score in [-1,1]; |net| must clear the threshold.

    These params are fixed a priori (textbook defaults), NOT fitted on any window.
    Optimisation with walk-forward arrives in a later phase.
    """

    agents: list[AgentSpec] = Field(
        default_factory=lambda: [
            AgentSpec(name="supertrend", weight=1.0, params={"period": 10, "multiplier": 3.0}),
            AgentSpec(name="macd", weight=1.0, params={"fast": 12, "slow": 26, "signal": 9}),
            AgentSpec(name="donchian", weight=1.0, params={"period": 20}),
        ]
    )
    entry_threshold: float = 0.5  # |net weighted score| required to take a position


class RegimeConfig(BaseModel):
    """Trend-vs-chop gate. A position is allowed ONLY in a trending regime.

    Defaults echo the project's 'Komutan shield': ADX >= 20 means trend present.
    """

    use_adx: bool = True
    adx_period: int = 14
    adx_threshold: float = 20.0
    use_efficiency_ratio: bool = True
    er_period: int = 10
    er_threshold: float = 0.30
    use_hurst: bool = False
    hurst_period: int = 100
    hurst_threshold: float = 0.50


class MTFConfig(BaseModel):
    """Higher-timeframe agreement filter. Long only if the higher TF also trends up."""

    enabled: bool = True
    higher_tf: str = "1d"
    method: Literal["supertrend"] = "supertrend"
    period: int = 10
    multiplier: float = 3.0


class MeanReversionConfig(BaseModel):
    """Counter-trend sleeve for CHOP regimes (the complement of the trend regime).

    Trend-following bleeds in choppy/ranging years; mean-reversion is its natural
    complement there. Enters on a z-score extreme of price vs its moving average,
    holds until price reverts toward the mean. Only active where regime = NOT trending.
    """

    sma_period: int = 20
    entry_z: float = 2.0  # |z| beyond this = stretched -> fade it
    exit_z: float = 0.5   # revert to within this band -> close


class OrchestratorConfig(BaseModel):
    """Which filters gate the ensemble signal into a final decision.

    gate_mode:
      * 'entry_only' (default) — filters block NEW entries only; an open position is
        managed by the stop/signal, NOT kicked out when the regime momentarily dips.
        Correct for trend-following: it doesn't chop winners short.
      * 'continuous' — filters force flat on every bar they disagree. Simpler, but
        fragments trends into churn (measured: it destroyed the in-sample edge).

    use_mr_sleeve: add the mean-reversion sleeve in chop bars (two-sleeve system:
      trend-following when trending, mean-reversion when not).
    """

    use_regime: bool = True
    use_mtf: bool = True
    gate_mode: Literal["entry_only", "continuous"] = "entry_only"
    use_mr_sleeve: bool = False


class MLConfig(BaseModel):
    """Signal-quality filter (LightGBM). Trained ONLY on the training window.

    Labels via triple-barrier (labels.py); features causal (features.py). The model
    predicts P(a long candidate reaches +TP before -stop within the horizon); entries
    below `threshold` are vetoed. Keep the model SMALL to resist overfitting — the
    honest test is OOS expectancy and the in/out AUC gap, not in-sample fit.
    """

    horizon_bars: int = 42  # triple-barrier vertical barrier (~7 days at 4h)
    threshold: float = 0.5  # min P(profitable) to allow a long entry
    tune_threshold: bool = True  # pick threshold on TRAIN by best expectancy proxy
    min_train_samples: int = 200
    # LightGBM hyperparameters (deliberately conservative).
    n_estimators: int = 200
    num_leaves: int = 15
    max_depth: int = 4
    learning_rate: float = 0.05
    min_child_samples: int = 50
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    reg_lambda: float = 1.0


class BacktestConfig(BaseModel):
    data: DataConfig = Field(default_factory=DataConfig)
    costs: CostConfig = Field(default_factory=CostConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    splits: SplitConfig = Field(default_factory=SplitConfig)
    ensemble: EnsembleConfig = Field(default_factory=EnsembleConfig)
    regime: RegimeConfig = Field(default_factory=RegimeConfig)
    mtf: MTFConfig = Field(default_factory=MTFConfig)
    mean_reversion: MeanReversionConfig = Field(default_factory=MeanReversionConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    ml: MLConfig = Field(default_factory=MLConfig)
    seed: int = 42

    @model_validator(mode="after")
    def _coherent(self) -> BacktestConfig:
        if self.data.market_type == "spot" and self.costs.funding_enabled:
            raise ValueError("funding_enabled requires market_type='perp'")
        return self


def load_config(path: str | Path) -> BacktestConfig:
    """Load and validate a YAML config into a BacktestConfig."""
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return BacktestConfig.model_validate(raw)
