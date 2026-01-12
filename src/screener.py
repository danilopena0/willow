"""Main screener script for options credit spread screening."""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import polars as pl

from src.models import CreditSpread, ScreenerConfig, ScreenerResult
from src.config import (
    load_config,
    RESULTS_DIR,
    HISTORY_DIR,
    DASHBOARDS_DIR,
)
from src.options_fetcher import OptionsFetcher
from src.spread_calculator import (
    screen_all_spreads,
    rank_spreads,
    filter_duplicate_strikes,
)
from src.visualizer import create_spread_dashboard, create_top_spreads_table
from src.alerter import send_alerts


def display_results(spreads: list[CreditSpread], max_display: int = 10) -> None:
    """
    Pretty print top spreads to console.

    Args:
        spreads: List of credit spreads to display
        max_display: Maximum number of spreads to show
    """
    if not spreads:
        print("\nNo spreads found matching criteria.")
        return

    print("\n" + "=" * 120)
    print(
        f"{'Ticker':<8} {'Type':<15} {'Strikes':<12} {'Credit':<10} "
        f"{'ROR %':<8} {'Max Loss':<10} {'DTE':<6} {'Dist %':<8} {'Break-Even':<12}"
    )
    print("=" * 120)

    for spread in spreads[:max_display]:
        print(
            f"{spread.ticker:<8} "
            f"{spread.spread_type.replace('_', ' ').title():<15} "
            f"${spread.short_leg.strike:.0f}/${spread.long_leg.strike:.0f}{'':>4} "
            f"${spread.net_credit:>6.2f}{'':>4} "
            f"{spread.return_on_risk:>5.1f}%{'':>3} "
            f"${spread.max_loss:>7.2f}{'':>3} "
            f"{spread.days_to_expiration:>4}{'':>2} "
            f"{spread.distance_from_price_pct:>5.1f}%{'':>2} "
            f"${spread.break_even:>8.2f}"
        )

    print("=" * 120)

    if len(spreads) > max_display:
        print(f"\n... and {len(spreads) - max_display} more spreads")


def save_results(spreads: list[CreditSpread], timestamp: datetime) -> str:
    """
    Save results to Excel with conditional formatting.

    Args:
        spreads: List of credit spreads to save
        timestamp: Timestamp for the screening run

    Returns:
        Path to saved Excel file
    """
    import xlsxwriter

    if not spreads:
        return ""

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    xlsx_filename = RESULTS_DIR / f"{timestamp.strftime('%Y%m%d_%H%M%S')}_spreads.xlsx"

    workbook = xlsxwriter.Workbook(str(xlsx_filename))
    worksheet = workbook.add_worksheet("Spreads")

    # Define formats
    header_fmt = workbook.add_format({
        "bold": True,
        "bg_color": "#4472C4",
        "font_color": "white",
        "border": 1,
        "align": "center",
    })
    money_fmt = workbook.add_format({"num_format": "$#,##0.00", "border": 1})
    pct_fmt = workbook.add_format({"num_format": "0.0%", "border": 1})
    num_fmt = workbook.add_format({"num_format": "#,##0", "border": 1})
    text_fmt = workbook.add_format({"border": 1})
    date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd", "border": 1})

    # Headers
    headers = [
        "Ticker", "Type", "Expiration", "DTE", "Short Strike", "Long Strike",
        "Credit", "Max Loss", "Max Profit", "ROR %", "Break-Even",
        "Stock Price", "Distance %", "Short OI", "Long OI"
    ]

    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_fmt)

    # Column widths (sized to fit headers)
    worksheet.set_column(0, 0, 10)   # Ticker
    worksheet.set_column(1, 1, 12)   # Type
    worksheet.set_column(2, 2, 12)   # Expiration
    worksheet.set_column(3, 3, 6)    # DTE
    worksheet.set_column(4, 4, 13)   # Short Strike
    worksheet.set_column(5, 5, 13)   # Long Strike
    worksheet.set_column(6, 6, 10)   # Credit
    worksheet.set_column(7, 7, 11)   # Max Loss
    worksheet.set_column(8, 8, 11)   # Max Profit
    worksheet.set_column(9, 9, 9)    # ROR %
    worksheet.set_column(10, 10, 12) # Break-Even
    worksheet.set_column(11, 11, 12) # Stock Price
    worksheet.set_column(12, 12, 12) # Distance %
    worksheet.set_column(13, 13, 10) # Short OI
    worksheet.set_column(14, 14, 10) # Long OI

    # Write data
    for row, spread in enumerate(spreads, start=1):
        worksheet.write(row, 0, spread.ticker, text_fmt)
        worksheet.write(row, 1, spread.spread_type.replace("_", " ").title(), text_fmt)
        worksheet.write(row, 2, spread.expiration, date_fmt)
        worksheet.write(row, 3, spread.days_to_expiration, num_fmt)
        worksheet.write(row, 4, spread.short_leg.strike, money_fmt)
        worksheet.write(row, 5, spread.long_leg.strike, money_fmt)
        worksheet.write(row, 6, spread.net_credit, money_fmt)
        worksheet.write(row, 7, spread.max_loss, money_fmt)
        worksheet.write(row, 8, spread.max_profit, money_fmt)
        worksheet.write(row, 9, spread.return_on_risk / 100, pct_fmt)
        worksheet.write(row, 10, spread.break_even, money_fmt)
        worksheet.write(row, 11, spread.current_stock_price, money_fmt)
        worksheet.write(row, 12, spread.distance_from_price_pct / 100, pct_fmt)
        worksheet.write(row, 13, spread.short_leg.open_interest, num_fmt)
        worksheet.write(row, 14, spread.long_leg.open_interest, num_fmt)

    # Conditional formatting with gradients
    last_row = len(spreads)

    # ROR % (column J, index 9) - Red to Green gradient (higher is better)
    worksheet.conditional_format(1, 9, last_row, 9, {
        "type": "3_color_scale",
        "min_type": "num",
        "mid_type": "num",
        "max_type": "num",
        "min_value": 0.15,
        "mid_value": 0.25,
        "max_value": 0.40,
        "min_color": "#F8696B",  # Red
        "mid_color": "#FFEB84",  # Yellow
        "max_color": "#63BE7B",  # Green
    })

    # DTE (column D, index 3) - Red to Green gradient (more time = better)
    worksheet.conditional_format(1, 3, last_row, 3, {
        "type": "3_color_scale",
        "min_type": "num",
        "mid_type": "num",
        "max_type": "num",
        "min_value": 14,
        "mid_value": 37,
        "max_value": 60,
        "min_color": "#F8696B",  # Red (less time)
        "mid_color": "#FFFFFF",  # White (middle)
        "max_color": "#63BE7B",  # Green (more time)
    })

    # Distance % (column M, index 12) - Red to Blue gradient (higher is safer)
    worksheet.conditional_format(1, 12, last_row, 12, {
        "type": "3_color_scale",
        "min_type": "num",
        "mid_type": "num",
        "max_type": "num",
        "min_value": 0.01,
        "mid_value": 0.05,
        "max_value": 0.10,
        "min_color": "#F8696B",  # Red (too close)
        "mid_color": "#FFEB84",  # Yellow
        "max_color": "#5B9BD5",  # Blue (safe)
    })

    # Freeze top row
    worksheet.freeze_panes(1, 0)

    # Auto-filter
    worksheet.autofilter(0, 0, last_row, len(headers) - 1)

    workbook.close()

    return str(xlsx_filename)


def screen_ticker(
    ticker: str,
    config: ScreenerConfig,
    fetcher: OptionsFetcher,
) -> list[CreditSpread]:
    """
    Screen a single ticker for credit spread opportunities.

    Args:
        ticker: Stock ticker symbol
        config: Screener configuration
        fetcher: Options fetcher instance

    Returns:
        List of qualifying credit spreads
    """
    all_spreads = []

    # Get expirations in range
    expirations = fetcher.get_expirations_in_range(
        ticker, config.min_dte, config.max_dte
    )

    if not expirations:
        return []

    for exp_str, dte in expirations:
        try:
            chain = fetcher.fetch_options_chain(ticker, exp_str)

            if chain.calls.is_empty() and chain.puts.is_empty():
                continue

            spreads = screen_all_spreads(
                calls=chain.calls,
                puts=chain.puts,
                ticker=ticker,
                stock_price=chain.stock_price,
                expiration=chain.expiration,
                dte=dte,
                config=config,
            )

            all_spreads.extend(spreads)

        except Exception as e:
            print(f"    Warning: Error processing {ticker} {exp_str}: {e}")
            continue

    return all_spreads


def run_screener(
    config: ScreenerConfig,
    visualize: bool = False,
    alert: bool = False,
    verbose: bool = True,
) -> ScreenerResult:
    """
    Run the full screening workflow.

    Args:
        config: Screener configuration
        visualize: Whether to generate visualizations
        alert: Whether to send alerts
        verbose: Whether to print progress

    Returns:
        ScreenerResult with all found spreads
    """
    timestamp = datetime.now()
    fetcher = OptionsFetcher()
    all_spreads = []
    tickers_with_errors = []

    if verbose:
        print(f"Screening {len(config.tickers)} tickers...")
        print(
            f"   Filters: ROR >= {config.min_return_on_risk}%, "
            f"DTE {config.min_dte}-{config.max_dte}, "
            f"Min Credit ${config.min_credit:.2f}"
        )
        print()

    for i, ticker in enumerate(config.tickers, 1):
        if verbose:
            print(f"  [{i}/{len(config.tickers)}] Analyzing {ticker}...", end=" ")

        try:
            spreads = screen_ticker(ticker, config, fetcher)
            all_spreads.extend(spreads)
            if verbose:
                print(f"Found {len(spreads)} spreads")

        except Exception as e:
            tickers_with_errors.append(ticker)
            if verbose:
                print(f"Error: {e}")
            continue

    # Remove duplicates and rank
    all_spreads = filter_duplicate_strikes(all_spreads)
    all_spreads = rank_spreads(all_spreads)

    if verbose:
        print(f"\nFound {len(all_spreads)} qualifying spreads total")

    # Display results
    if verbose and all_spreads:
        display_results(all_spreads, max_display=10)

    # Save results
    xlsx_path = save_results(all_spreads, timestamp)
    if verbose and xlsx_path:
        print(f"Results saved to {xlsx_path}")

    # Generate visualizations
    dashboard_path = None
    if visualize and all_spreads:
        if verbose:
            print("\nGenerating visualizations...")

        DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
        dashboard_path = create_spread_dashboard(all_spreads, DASHBOARDS_DIR)

        if verbose:
            print(f"   Dashboard: {dashboard_path}")

        table_fig = create_top_spreads_table(all_spreads)
        table_path = DASHBOARDS_DIR / f"top_spreads_{timestamp.strftime('%Y%m%d_%H%M%S')}.html"
        table_fig.save(str(table_path))

        if verbose:
            print(f"   Table: {table_path}")

    # Send alerts
    if alert and all_spreads:
        high_quality = [
            s for s in all_spreads if s.return_on_risk > config.alert_threshold_ror
        ]

        if high_quality:
            if verbose:
                print(f"\nSending alert for {len(high_quality)} high-quality spreads...")

            results = send_alerts(
                high_quality,
                enable_slack=config.enable_slack_alerts,
                dashboard_path=dashboard_path,
            )

            if verbose:
                if results["slack"]:
                    print("   Slack message sent successfully")
                else:
                    print("   No alerts configured or sent")

    return ScreenerResult(
        timestamp=timestamp,
        config=config,
        spreads=all_spreads,
        tickers_screened=len(config.tickers),
        tickers_with_errors=tickers_with_errors,
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Screen options for credit spread opportunities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.screener
  python -m src.screener --tickers AAPL MSFT GOOGL
  python -m src.screener --min-ror 25 --max-dte 60
  python -m src.screener --visualize --alert
        """,
    )

    parser.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        help="List of tickers to screen (default: use config)",
    )

    parser.add_argument(
        "--min-ror",
        type=float,
        default=None,
        help="Minimum return on risk percentage (default: 20)",
    )

    parser.add_argument(
        "--min-dte",
        type=int,
        default=None,
        help="Minimum days to expiration (default: 30)",
    )

    parser.add_argument(
        "--max-dte",
        type=int,
        default=None,
        help="Maximum days to expiration (default: 45)",
    )

    parser.add_argument(
        "--min-credit",
        type=float,
        default=None,
        help="Minimum net credit (default: 0.30)",
    )

    parser.add_argument(
        "--max-loss",
        type=float,
        default=None,
        help="Maximum loss per spread (default: 500)",
    )

    parser.add_argument(
        "--spread-width",
        type=int,
        default=None,
        help="Width between strikes in dollars (default: 5)",
    )

    parser.add_argument(
        "--min-oi",
        type=int,
        default=None,
        help="Minimum open interest (default: 50)",
    )

    parser.add_argument(
        "--visualize",
        "-v",
        action="store_true",
        help="Generate Altair dashboard and charts",
    )

    parser.add_argument(
        "--alert",
        "-a",
        action="store_true",
        help="Send alerts for qualifying spreads",
    )

    parser.add_argument(
        "--slack",
        action="store_true",
        help="Enable Slack alerts (requires SLACK_WEBHOOK_URL env var)",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output",
    )

    parser.add_argument(
        "--test-alerts",
        action="store_true",
        help="Test alert configuration and exit",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Test alerts mode
    if args.test_alerts:
        from src.alerter import test_slack_connection

        print("Testing Slack configuration...")
        test_slack_connection()
        return 0

    # Load base config
    config = load_config()

    # Apply CLI overrides
    if args.tickers:
        config.tickers = [t.upper() for t in args.tickers]
    if args.min_ror is not None:
        config.min_return_on_risk = args.min_ror
    if args.min_dte is not None:
        config.min_dte = args.min_dte
    if args.max_dte is not None:
        config.max_dte = args.max_dte
    if args.min_credit is not None:
        config.min_credit = args.min_credit
    if args.max_loss is not None:
        config.max_loss = args.max_loss
    if args.spread_width is not None:
        config.spread_width = args.spread_width
    if args.min_oi is not None:
        config.min_open_interest = args.min_oi

    # Alert settings
    if args.slack:
        config.enable_slack_alerts = True

    # Run screener
    try:
        result = run_screener(
            config=config,
            visualize=args.visualize,
            alert=args.alert,
            verbose=not args.quiet,
        )

        if not args.quiet:
            print(f"\nScreening complete:")
            print(f"  Tickers screened: {result.tickers_screened}")
            print(f"  Total spreads found: {result.total_spreads}")
            print(f"  Bull put spreads: {result.bull_put_count}")
            print(f"  Bear call spreads: {result.bear_call_count}")
            if result.spreads:
                print(f"  Average ROR: {result.avg_return_on_risk:.1f}%")
            if result.tickers_with_errors:
                print(f"  Tickers with errors: {', '.join(result.tickers_with_errors)}")

        return 0

    except KeyboardInterrupt:
        print("\nScreening interrupted by user")
        return 130

    except Exception as e:
        print(f"\nError: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
