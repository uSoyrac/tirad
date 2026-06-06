"""Render metrics as a side-by-side in-sample vs out-of-sample table.

The whole point of the project is that gap. So the report puts in-sample and OOS
columns next to each other for every strategy and never hides the ugly rows.
"""

from __future__ import annotations

_ROWS = [
    ("total_return", "Total return", "pct"),
    ("cagr", "CAGR", "pct"),
    ("sharpe", "Sharpe", "num"),
    ("sortino", "Sortino", "num"),
    ("max_drawdown", "Max drawdown", "pct"),
    ("win_rate", "Win rate", "pct"),
    ("avg_win", "Avg win ($)", "cur"),
    ("avg_loss", "Avg loss ($)", "cur"),
    ("expectancy", "Expectancy ($/trade)", "cur"),
    ("payoff_ratio", "Payoff ratio", "num"),
    ("longest_losing_streak", "Longest losing streak", "int"),
    ("risk_of_ruin", "Risk of ruin (MC)", "pct"),
    ("n_trades", "Trades", "int"),
]


def _fmt(val, kind: str) -> str:
    if val is None:
        return "-"
    try:
        f = float(val)
    except (TypeError, ValueError):
        return str(val)
    if f != f:  # nan
        return "n/a"
    if kind == "pct":
        return f"{f * 100:.2f}%"
    if kind == "cur":
        return f"{f:,.2f}"
    if kind == "int":
        return f"{int(f)}"
    return f"{f:.3f}"


def render_table(title: str, columns: dict[str, dict]) -> str:
    """columns: {column_label: metrics_dict}. Renders a markdown table."""
    labels = list(columns.keys())
    header = "| Metric | " + " | ".join(labels) + " |"
    sep = "|" + "---|" * (len(labels) + 1)
    lines = [f"### {title}", "", header, sep]
    for key, label, kind in _ROWS:
        cells = [_fmt(columns[c].get(key), kind) for c in labels]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_report(title: str, sections: list[tuple[str, dict[str, dict]]]) -> str:
    parts = [f"# {title}", ""]
    for sec_title, cols in sections:
        parts.append(render_table(sec_title, cols))
        parts.append("")
    return "\n".join(parts)
