"""Main screener script for options credit spread screening."""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import NamedTuple

from src.models import CreditSpread, ScreenerConfig, ScreenerResult


from src.config import (
    load_config,
    RESULTS_DIR,
    DASHBOARDS_DIR,
)
from src.constants import SCREENING
from src.options_fetcher import OptionsFetcher
from src.spread_calculator import (
    screen_all_spreads,
    rank_spreads,
    filter_duplicate_strikes,
)
from src.visualizer import create_spread_dashboard, create_top_spreads_table
from src.alerter import send_alerts
from src.excel_exporter import export_to_excel


class TickerResult(NamedTuple):
    """Result from screening a single ticker."""
    ticker: str
    spreads: list[CreditSpread]
    error: str | None = None
    skipped_earnings: bool = False


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

    print("\n" + "=" * 140)
    print(
        f"{'Ticker':<8} {'Type':<12} {'Strikes':<12} {'Width':<6} {'Credit':<8} "
        f"{'ROR %':<7} {'Ann %':<8} {'POP %':<6} {'DTE':<5} {'Dist %':<7} {'Max Loss':<10}"
    )
    print("=" * 140)

    for spread in spreads[:max_display]:
        print(
            f"{spread.ticker:<8} "
            f"{spread.spread_type.replace('_', ' ').title():<12} "
            f"${spread.short_leg.strike:.0f}/${spread.long_leg.strike:.0f}{'':>3} "
            f"${spread.width:<5.0f} "
            f"${spread.net_credit:<6.2f} "
            f"{spread.return_on_risk:>5.1f}%  "
            f"{spread.annualized_return:>6.1f}%  "
            f"{spread.probability_of_profit:>4.0f}%  "
            f"{spread.days_to_expiration:>3}   "
            f"{spread.distance_from_price_pct:>5.1f}%  "
            f"${spread.max_loss:>7.2f}"
        )

    print("=" * 140)

    if len(spreads) > max_display:
        print(f"\n... and {len(spreads) - max_display} more spreads")


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


def _screen_ticker_task(
    ticker: str,
    config: ScreenerConfig,
    fetcher: OptionsFetcher,
) -> TickerResult:
    """
    Screen a single ticker (for use in parallel execution).

    Returns:
        TickerResult with spreads or error information
    """
    try:
        # Check for upcoming earnings
        if config.earnings_buffer_days > 0:
            if fetcher.has_earnings_soon(ticker, config.earnings_buffer_days):
                return TickerResult(ticker=ticker, spreads=[], skipped_earnings=True)

        spreads = screen_ticker(ticker, config, fetcher)
        return TickerResult(ticker=ticker, spreads=spreads)

    except Exception as e:
        return TickerResult(ticker=ticker, spreads=[], error=str(e))


def run_screener(
    config: ScreenerConfig,
    fetcher: OptionsFetcher | None = None,
    visualize: bool = False,
    alert: bool = False,
    verbose: bool = True,
    parallel: bool = True,
) -> ScreenerResult:
    """
    Run the full screening workflow.

    Args:
        config: Screener configuration
        fetcher: Options data fetcher (created if not provided)
        visualize: Whether to generate visualizations
        alert: Whether to send alerts
        verbose: Whether to print progress
        parallel: Whether to use parallel fetching

    Returns:
        ScreenerResult with all found spreads
    """
    timestamp = datetime.now()
    fetcher = fetcher or OptionsFetcher()
    all_spreads = []
    tickers_with_errors = []
    tickers_skipped_earnings = []

    if verbose:
        print(f"Screening {len(config.tickers)} tickers...")
        print(
            f"   Filters: ROR {config.min_return_on_risk}-{config.max_return_on_risk}%, "
            f"Dist >= {config.min_distance_pct}%, "
            f"DTE {config.min_dte}-{config.max_dte}, "
            f"Widths: ${', $'.join(str(w) for w in config.spread_widths)}"
        )
        if config.earnings_buffer_days > 0:
            print(f"   Earnings filter: Skip if earnings within {config.earnings_buffer_days} days")
        if parallel:
            print(f"   Mode: Parallel ({SCREENING.MAX_PARALLEL_WORKERS} workers)")
        print()

    if parallel and len(config.tickers) > 1:
        # Parallel execution with ThreadPoolExecutor
        completed = 0
        with ThreadPoolExecutor(max_workers=SCREENING.MAX_PARALLEL_WORKERS) as executor:
            # Submit all tasks
            future_to_ticker = {
                executor.submit(_screen_ticker_task, ticker, config, fetcher): ticker
                for ticker in config.tickers
            }

            # Process results as they complete
            for future in as_completed(future_to_ticker):
                result = future.result()
                completed += 1

                if verbose:
                    status = ""
                    if result.skipped_earnings:
                        status = "Skipped (earnings)"
                        tickers_skipped_earnings.append(result.ticker)
                    elif result.error:
                        status = f"Error: {result.error}"
                        tickers_with_errors.append(result.ticker)
                    else:
                        status = f"Found {len(result.spreads)} spreads"
                        all_spreads.extend(result.spreads)

                    print(f"  [{completed}/{len(config.tickers)}] {result.ticker}: {status}")
    else:
        # Sequential execution
        for i, ticker in enumerate(config.tickers, 1):
            if verbose:
                print(f"  [{i}/{len(config.tickers)}] Analyzing {ticker}...", end=" ")

            result = _screen_ticker_task(ticker, config, fetcher)

            if result.skipped_earnings:
                tickers_skipped_earnings.append(ticker)
                if verbose:
                    print("Skipped (earnings soon)")
            elif result.error:
                tickers_with_errors.append(ticker)
                if verbose:
                    print(f"Error: {result.error}")
            else:
                all_spreads.extend(result.spreads)
                if verbose:
                    print(f"Found {len(result.spreads)} spreads")

    # Remove duplicates and rank
    all_spreads = filter_duplicate_strikes(all_spreads)
    all_spreads = rank_spreads(all_spreads)

    if verbose:
        print(f"\nFound {len(all_spreads)} qualifying spreads total")
        if tickers_skipped_earnings:
            print(f"Skipped {len(tickers_skipped_earnings)} tickers due to upcoming earnings: {', '.join(tickers_skipped_earnings)}")

    # Display results
    if verbose and all_spreads:
        display_results(all_spreads, max_display=10)

    # Save results
    xlsx_path = export_to_excel(all_spreads, RESULTS_DIR, timestamp)
    if verbose and xlsx_path:
        print(f"\nResults saved to {xlsx_path}")

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
  python -m src.screener --widths 1 2 5 10
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
        "--max-ror",
        type=float,
        default=None,
        help="Maximum return on risk percentage (default: 75)",
    )

    parser.add_argument(
        "--min-distance",
        type=float,
        default=None,
        help="Minimum distance from price as percentage (default: 5)",
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
        help="Minimum net credit (default: 0.20)",
    )

    parser.add_argument(
        "--max-loss",
        type=float,
        default=None,
        help="Maximum loss per spread (default: 500)",
    )

    parser.add_argument(
        "--widths",
        nargs="+",
        type=int,
        default=None,
        help="Spread widths to scan in dollars (default: 1 2 5)",
    )

    parser.add_argument(
        "--earnings-buffer",
        type=int,
        default=None,
        help="Skip tickers with earnings within N days (default: 7, use 0 to disable)",
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
    if args.max_ror is not None:
        config.max_return_on_risk = args.max_ror
    if args.min_distance is not None:
        config.min_distance_pct = args.min_distance
    if args.min_dte is not None:
        config.min_dte = args.min_dte
    if args.max_dte is not None:
        config.max_dte = args.max_dte
    if args.min_credit is not None:
        config.min_credit = args.min_credit
    if args.max_loss is not None:
        config.max_loss = args.max_loss
    if args.widths is not None:
        config.spread_widths = args.widths
    if args.earnings_buffer is not None:
        config.earnings_buffer_days = args.earnings_buffer
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
