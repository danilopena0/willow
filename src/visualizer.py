"""Altair visualizations for credit spread analysis."""

from datetime import datetime
from pathlib import Path

import altair as alt
import polars as pl

from src.models import CreditSpread
from src.config import DASHBOARDS_DIR

# Enable saving to HTML
alt.data_transformers.enable("vegafusion")


def spreads_to_dataframe(spreads: list[CreditSpread]) -> pl.DataFrame:
    """Convert list of spreads to a Polars DataFrame for charting."""
    if not spreads:
        return pl.DataFrame()

    records = []
    for s in spreads:
        records.append({
            "ticker": s.ticker,
            "spread_type": s.spread_type.replace("_", " ").title(),
            "expiration": s.expiration,
            "days_to_expiration": s.days_to_expiration,
            "short_strike": s.short_leg.strike,
            "long_strike": s.long_leg.strike,
            "net_credit": s.net_credit,
            "max_loss": s.max_loss,
            "max_profit": s.max_profit,
            "return_on_risk": s.return_on_risk,
            "break_even": s.break_even,
            "current_price": s.current_stock_price,
            "distance_pct": s.distance_from_price_pct,
        })

    return pl.DataFrame(records)


def create_spread_dashboard(
    spreads: list[CreditSpread],
    output_dir: str | Path | None = None,
) -> str:
    """
    Generate interactive HTML dashboard with multiple views.

    Args:
        spreads: List of credit spreads to visualize
        output_dir: Directory to save the dashboard

    Returns:
        Path to the saved dashboard HTML file
    """
    if output_dir is None:
        output_dir = DASHBOARDS_DIR

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = output_dir / f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

    if not spreads:
        # Create empty chart with message
        empty_chart = alt.Chart().mark_text(
            text="No spreads found matching criteria",
            fontSize=20
        ).properties(width=600, height=400, title="Credit Spread Dashboard - No Data")

        empty_chart.save(str(filename))
        return str(filename)

    df = spreads_to_dataframe(spreads).to_pandas()

    # 1. Scatter: Return on Risk vs Max Loss
    scatter = alt.Chart(df).mark_circle(size=100).encode(
        x=alt.X("max_loss:Q", title="Max Loss ($)"),
        y=alt.Y("return_on_risk:Q", title="Return on Risk (%)"),
        color=alt.Color("days_to_expiration:Q", scale=alt.Scale(scheme="viridis"), title="DTE"),
        tooltip=[
            alt.Tooltip("ticker:N", title="Ticker"),
            alt.Tooltip("spread_type:N", title="Type"),
            alt.Tooltip("max_loss:Q", title="Max Loss", format="$.2f"),
            alt.Tooltip("return_on_risk:Q", title="ROR", format=".1f"),
            alt.Tooltip("days_to_expiration:Q", title="DTE"),
        ],
    ).properties(
        width=350,
        height=250,
        title="Return on Risk vs Max Loss"
    )

    # 2. Bar: Average Return by Ticker
    ticker_avg = alt.Chart(df).mark_bar(color="steelblue").encode(
        x=alt.X("ticker:N", title="Ticker", sort="-y"),
        y=alt.Y("mean(return_on_risk):Q", title="Avg Return on Risk (%)"),
        tooltip=[
            alt.Tooltip("ticker:N", title="Ticker"),
            alt.Tooltip("mean(return_on_risk):Q", title="Avg ROR", format=".1f"),
            alt.Tooltip("count():Q", title="Count"),
        ],
    ).properties(
        width=350,
        height=250,
        title="Average Return by Ticker"
    )

    # 3. Histogram: Days to Expiration Distribution
    dte_hist = alt.Chart(df).mark_bar(color="lightgreen").encode(
        x=alt.X("days_to_expiration:Q", bin=alt.Bin(maxbins=10), title="Days to Expiration"),
        y=alt.Y("count():Q", title="Count"),
        tooltip=[
            alt.Tooltip("days_to_expiration:Q", bin=alt.Bin(maxbins=10), title="DTE Range"),
            alt.Tooltip("count():Q", title="Count"),
        ],
    ).properties(
        width=350,
        height=250,
        title="DTE Distribution"
    )

    # 4. Pie/Donut: Spread Type Breakdown (using arc mark)
    type_counts = df.groupby("spread_type").size().reset_index(name="count")

    pie = alt.Chart(type_counts).mark_arc(innerRadius=50).encode(
        theta=alt.Theta("count:Q"),
        color=alt.Color("spread_type:N", title="Spread Type"),
        tooltip=[
            alt.Tooltip("spread_type:N", title="Type"),
            alt.Tooltip("count:Q", title="Count"),
        ],
    ).properties(
        width=250,
        height=250,
        title="Spread Type Breakdown"
    )

    # Combine into dashboard layout
    top_row = scatter | ticker_avg
    bottom_row = dte_hist | pie

    dashboard = alt.vconcat(
        top_row,
        bottom_row,
        title=alt.Title(
            text=f"Credit Spread Analysis - {len(spreads)} Opportunities Found",
            fontSize=18,
        )
    ).configure_view(
        strokeWidth=0
    ).configure_axis(
        labelFontSize=11,
        titleFontSize=12
    )

    dashboard.save(str(filename))
    return str(filename)


def create_individual_spread_chart(
    spread: CreditSpread,
    price_history: pl.DataFrame | None = None,
) -> alt.Chart:
    """
    Create detailed chart for a single spread showing price action and strike levels.

    Args:
        spread: The credit spread to visualize
        price_history: Historical price data (optional)

    Returns:
        Altair Chart object
    """
    charts = []

    # Price history line chart
    if price_history is not None and not price_history.is_empty():
        hist_df = price_history.to_pandas()

        price_line = alt.Chart(hist_df).mark_line(color="steelblue").encode(
            x=alt.X("date:T", title="Date"),
            y=alt.Y("close:Q", title="Price ($)", scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("close:Q", title="Close", format="$.2f"),
            ],
        )
        charts.append(price_line)

    # Create horizontal rules for strike levels
    rules_data = [
        {"price": spread.current_stock_price, "label": f"Current: ${spread.current_stock_price:.2f}", "type": "current"},
        {"price": spread.short_leg.strike, "label": f"Short: ${spread.short_leg.strike:.0f}", "type": "short"},
        {"price": spread.long_leg.strike, "label": f"Long: ${spread.long_leg.strike:.0f}", "type": "long"},
        {"price": spread.break_even, "label": f"Break-Even: ${spread.break_even:.2f}", "type": "breakeven"},
    ]
    rules_df = pl.DataFrame(rules_data).to_pandas()

    color_scale = alt.Scale(
        domain=["current", "short", "long", "breakeven"],
        range=["blue", "red", "green", "orange"]
    )

    rules = alt.Chart(rules_df).mark_rule(strokeDash=[5, 5]).encode(
        y=alt.Y("price:Q"),
        color=alt.Color("type:N", scale=color_scale, legend=None),
        tooltip=["label:N"],
    )

    labels = alt.Chart(rules_df).mark_text(align="left", dx=5).encode(
        y=alt.Y("price:Q"),
        text="label:N",
        color=alt.Color("type:N", scale=color_scale, legend=None),
    )

    if charts:
        base = charts[0]
        chart = (base + rules + labels)
    else:
        # If no price history, just show the rules
        chart = (rules + labels)

    chart = chart.properties(
        width=600,
        height=400,
        title=alt.Title(
            text=f"{spread.ticker} - {spread.spread_type.replace('_', ' ').title()}",
            subtitle=f"Credit: ${spread.net_credit:.2f} | ROR: {spread.return_on_risk:.1f}% | DTE: {spread.days_to_expiration}",
        )
    )

    return chart


def create_top_spreads_table(
    spreads: list[CreditSpread],
    top_n: int = 10,
) -> alt.Chart:
    """
    Create a visual table of top spreads using Altair text marks.

    Args:
        spreads: List of credit spreads
        top_n: Number of top spreads to show

    Returns:
        Altair Chart with table visualization
    """
    top = spreads[:top_n]

    if not top:
        return alt.Chart().mark_text(
            text="No spreads to display",
            fontSize=16
        ).properties(width=600, height=100)

    # Prepare table data
    rows = []
    for i, s in enumerate(top):
        rows.append({
            "rank": i + 1,
            "ticker": s.ticker,
            "type": s.spread_type.replace("_", " ").title(),
            "strikes": f"${s.short_leg.strike:.0f}/${s.long_leg.strike:.0f}",
            "credit": f"${s.net_credit:.2f}",
            "max_loss": f"${s.max_loss:.2f}",
            "ror": f"{s.return_on_risk:.1f}%",
            "dte": str(s.days_to_expiration),
            "ror_value": s.return_on_risk,  # For color encoding
        })

    df = pl.DataFrame(rows).to_pandas()

    # Create a heatmap-style table
    base = alt.Chart(df).encode(
        y=alt.Y("rank:O", title=None, axis=alt.Axis(labels=False, ticks=False)),
    )

    # Text columns
    columns = [
        ("ticker", "Ticker", 60),
        ("type", "Type", 80),
        ("strikes", "Strikes", 80),
        ("credit", "Credit", 60),
        ("max_loss", "Max Loss", 70),
        ("ror", "ROR", 50),
        ("dte", "DTE", 40),
    ]

    text_charts = []
    x_offset = 0

    for col, title, width in columns:
        # Header
        header = alt.Chart({"values": [{"text": title}]}).mark_text(
            fontWeight="bold",
            fontSize=12,
        ).encode(
            text="text:N"
        ).properties(width=width, height=20)

        # Values with conditional color for ROR
        if col == "ror":
            text = base.mark_text(fontSize=11).encode(
                text=f"{col}:N",
                color=alt.condition(
                    alt.datum.ror_value > 30,
                    alt.value("green"),
                    alt.value("black")
                )
            ).properties(width=width, height=25 * len(df))
        else:
            text = base.mark_text(fontSize=11).encode(
                text=f"{col}:N",
            ).properties(width=width, height=25 * len(df))

        col_chart = alt.vconcat(header, text, spacing=0)
        text_charts.append(col_chart)

    table = alt.hconcat(*text_charts, spacing=5).properties(
        title=alt.Title(
            text=f"Top {len(top)} Credit Spreads by Return on Risk",
            fontSize=14,
        )
    )

    return table


def create_payoff_diagram(spread: CreditSpread) -> alt.Chart:
    """
    Create a payoff diagram for a credit spread.

    Args:
        spread: The credit spread to visualize

    Returns:
        Altair Chart showing P&L at expiration
    """
    short_strike = spread.short_leg.strike
    long_strike = spread.long_leg.strike

    # Generate price range
    if spread.spread_type == "bull_put":
        min_price = long_strike * 0.9
        max_price = short_strike * 1.1
    else:
        min_price = short_strike * 0.9
        max_price = long_strike * 1.1

    # Calculate P&L at each price point
    prices = []
    pnls = []
    step = (max_price - min_price) / 100

    current_price = min_price
    while current_price <= max_price:
        prices.append(current_price)

        if spread.spread_type == "bull_put":
            if current_price >= short_strike:
                profit = spread.net_credit * 100
            elif current_price <= long_strike:
                profit = -spread.max_loss
            else:
                profit = (spread.net_credit - (short_strike - current_price)) * 100
        else:  # bear_call
            if current_price <= short_strike:
                profit = spread.net_credit * 100
            elif current_price >= long_strike:
                profit = -spread.max_loss
            else:
                profit = (spread.net_credit - (current_price - short_strike)) * 100

        pnls.append(profit)
        current_price += step

    payoff_df = pl.DataFrame({"price": prices, "pnl": pnls}).to_pandas()

    # Payoff line with area fill
    payoff_line = alt.Chart(payoff_df).mark_area(
        line={"color": "steelblue"},
        opacity=0.3,
        color=alt.Gradient(
            gradient="linear",
            stops=[
                alt.GradientStop(color="red", offset=0),
                alt.GradientStop(color="white", offset=0.5),
                alt.GradientStop(color="green", offset=1),
            ],
            x1=1, x2=1, y1=1, y2=0
        )
    ).encode(
        x=alt.X("price:Q", title="Stock Price at Expiration ($)"),
        y=alt.Y("pnl:Q", title="Profit/Loss ($)"),
        tooltip=[
            alt.Tooltip("price:Q", title="Price", format="$.2f"),
            alt.Tooltip("pnl:Q", title="P&L", format="$.2f"),
        ],
    )

    # Zero line
    zero_line = alt.Chart({"values": [{"y": 0}]}).mark_rule(
        color="gray", strokeDash=[3, 3]
    ).encode(y="y:Q")

    # Vertical markers for key prices
    markers_data = [
        {"x": spread.current_stock_price, "label": f"Current: ${spread.current_stock_price:.2f}"},
        {"x": short_strike, "label": f"Short: ${short_strike:.0f}"},
        {"x": long_strike, "label": f"Long: ${long_strike:.0f}"},
        {"x": spread.break_even, "label": f"BE: ${spread.break_even:.2f}"},
    ]
    markers_df = pl.DataFrame(markers_data).to_pandas()

    markers = alt.Chart(markers_df).mark_rule(strokeDash=[5, 5], opacity=0.7).encode(
        x="x:Q",
        tooltip=["label:N"],
    )

    chart = (payoff_line + zero_line + markers).properties(
        width=500,
        height=300,
        title=alt.Title(
            text=f"{spread.ticker} {spread.spread_type.replace('_', ' ').title()} - Payoff at Expiration",
            subtitle=f"Max Profit: ${spread.max_profit:.2f} | Max Loss: ${spread.max_loss:.2f}",
        )
    )

    return chart


def save_all_visualizations(
    spreads: list[CreditSpread],
    output_dir: str | Path | None = None,
) -> dict[str, str]:
    """
    Generate and save all visualizations.

    Args:
        spreads: List of credit spreads
        output_dir: Directory to save files

    Returns:
        Dictionary mapping visualization names to file paths
    """
    if output_dir is None:
        output_dir = DASHBOARDS_DIR

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_files = {}

    # Main dashboard
    dashboard_path = create_spread_dashboard(spreads, output_dir)
    saved_files["dashboard"] = dashboard_path

    # Top spreads table
    if spreads:
        table_chart = create_top_spreads_table(spreads)
        table_path = output_dir / f"top_spreads_{timestamp}.html"
        table_chart.save(str(table_path))
        saved_files["table"] = str(table_path)

        # Individual payoff diagrams for top 5
        for i, spread in enumerate(spreads[:5]):
            payoff_chart = create_payoff_diagram(spread)
            payoff_path = output_dir / f"payoff_{spread.ticker}_{i}_{timestamp}.html"
            payoff_chart.save(str(payoff_path))
            saved_files[f"payoff_{spread.ticker}_{i}"] = str(payoff_path)

    return saved_files
