"""Interactive candlestick chart with SMC supply/demand zones."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

import config
from zone_detector import ZoneDict

# Colour constants
_DEMAND_FILL_NORMAL = "rgba(0, 200, 83, 0.15)"
_DEMAND_FILL_HIGH = "rgba(0, 200, 83, 0.25)"
_DEMAND_BORDER_NORMAL = "rgba(0, 200, 83, 0.6)"
_DEMAND_BORDER_HIGH = "rgba(0, 230, 100, 1.0)"

_SUPPLY_FILL_NORMAL = "rgba(255, 23, 68, 0.15)"
_SUPPLY_FILL_HIGH = "rgba(255, 23, 68, 0.25)"
_SUPPLY_BORDER_NORMAL = "rgba(255, 23, 68, 0.6)"
_SUPPLY_BORDER_HIGH = "rgba(255, 80, 100, 1.0)"

_BG_PLOT = "#0D0D0D"
_BG_PAPER = "#1A1A1A"
_GRID_COLOR = "#2A2A2A"
_TEXT_COLOR = "#CCCCCC"


def plot_zones(df: pd.DataFrame, zones: list[ZoneDict]) -> None:
    """Plot candlesticks and SMC zones on an interactive Plotly chart.

    Args:
        df: OHLCV DataFrame with columns ``[datetime, open, high, low, close, volume]``.
        zones: List of zone dicts as returned by :func:`zone_detector.find_zones`.
    """
    last_dt = df["datetime"].iloc[-1]
    first_dt = df["datetime"].iloc[0]

    fig = go.Figure()

    # --- Candlesticks ---
    fig.add_trace(
        go.Candlestick(
            x=df["datetime"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Price",
            increasing_line_color="#26A69A",
            decreasing_line_color="#EF5350",
            increasing_fillcolor="#26A69A",
            decreasing_fillcolor="#EF5350",
        )
    )

    # Track legend entries to avoid duplicates
    demand_legend_shown = False
    supply_legend_shown = False

    for zone in zones:
        is_demand = zone["type"] == "demand"
        is_high_prob = zone["score"] >= 5

        if is_demand:
            fill_color = _DEMAND_FILL_HIGH if is_high_prob else _DEMAND_FILL_NORMAL
            border_color = _DEMAND_BORDER_HIGH if is_high_prob else _DEMAND_BORDER_NORMAL
            label_prefix = "🔥 DEMAND" if is_high_prob else "DEMAND"
            legend_name = "Demand Zone"
            show_legend = not demand_legend_shown
            demand_legend_shown = True
        else:
            fill_color = _SUPPLY_FILL_HIGH if is_high_prob else _SUPPLY_FILL_NORMAL
            border_color = _SUPPLY_BORDER_HIGH if is_high_prob else _SUPPLY_BORDER_NORMAL
            label_prefix = "🔥 SUPPLY" if is_high_prob else "SUPPLY"
            legend_name = "Supply Zone"
            show_legend = not supply_legend_shown
            supply_legend_shown = True

        # Filled rectangle spanning from zone start to last bar
        fig.add_shape(
            type="rect",
            xref="x",
            yref="y",
            x0=zone["datetime_start"],
            x1=last_dt,
            y0=zone["zone_low"],
            y1=zone["zone_high"],
            fillcolor=fill_color,
            line=dict(color=border_color, width=1),
            layer="below",
        )

        # Text annotation at the left edge of the zone
        annotation_text = (
            f"{label_prefix} — {zone['probability']} ({zone['score']:.1f})"
        )
        fig.add_annotation(
            x=zone["datetime_start"],
            y=zone["zone_mid"],
            text=annotation_text,
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            font=dict(
                color=_DEMAND_BORDER_HIGH if is_demand else _SUPPLY_BORDER_HIGH,
                size=10,
            ),
            bgcolor="rgba(13, 13, 13, 0.6)",
        )

        # Invisible scatter trace for legend entry (one per type)
        if show_legend:
            fig.add_trace(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode="markers",
                    marker=dict(
                        size=12,
                        color=fill_color,
                        symbol="square",
                        line=dict(color=border_color, width=2),
                    ),
                    name=legend_name,
                    showlegend=True,
                )
            )

    if not zones:
        fig.add_annotation(
            text="No SMC zones detected — try lowering MIN_SCORE in config.py",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color=_TEXT_COLOR, size=14),
        )

    # --- Layout ---
    title_text = (
        f"SMC Zones | {config.INSTRUMENT} | {config.INTERVAL} | "
        f"{len(zones)} zone{'s' if len(zones) != 1 else ''} detected"
    )

    fig.update_layout(
        title=dict(text=title_text, font=dict(color=_TEXT_COLOR, size=16)),
        paper_bgcolor=_BG_PAPER,
        plot_bgcolor=_BG_PLOT,
        xaxis=dict(
            rangeslider=dict(visible=False),
            gridcolor=_GRID_COLOR,
            color=_TEXT_COLOR,
            showgrid=True,
        ),
        yaxis=dict(
            gridcolor=_GRID_COLOR,
            color=_TEXT_COLOR,
            showgrid=True,
            side="right",
        ),
        legend=dict(
            bgcolor="rgba(26, 26, 26, 0.8)",
            bordercolor=_GRID_COLOR,
            borderwidth=1,
            font=dict(color=_TEXT_COLOR),
        ),
        hovermode="x unified",
        margin=dict(l=20, r=60, t=60, b=20),
    )

    fig.show()
