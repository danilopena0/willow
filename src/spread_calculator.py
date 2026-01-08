"""Spread calculation and screening logic using Polars."""

from datetime import date

import polars as pl

from src.models import CreditSpread, OptionLeg, ScreenerConfig
from src.config import SPREAD_TYPE_BULL_PUT, SPREAD_TYPE_BEAR_CALL


def create_option_leg(row: dict) -> OptionLeg:
    """Create an OptionLeg from a DataFrame row dictionary."""
    return OptionLeg(
        strike=row.get("strike", 0.0),
        premium=row.get("premium", 0.0),
        bid=row.get("bid", 0.0),
        ask=row.get("ask", 0.0),
        delta=row.get("delta"),
        implied_volatility=row.get("implied_volatility"),
        open_interest=int(row.get("open_interest", 0) or 0),
        volume=int(row.get("volume", 0) or 0),
        contract_symbol=row.get("contract_symbol"),
    )


def screen_bull_put_spreads(
    puts: pl.DataFrame,
    ticker: str,
    stock_price: float,
    expiration: date,
    dte: int,
    config: ScreenerConfig,
) -> list[CreditSpread]:
    """
    Screen for bull put spreads (bullish strategy).

    A bull put spread involves:
    - Selling a put at a higher strike (short leg)
    - Buying a put at a lower strike (long leg)
    - Net credit received upfront
    - Profitable when stock stays above short strike

    Args:
        puts: DataFrame of put options
        ticker: Stock ticker symbol
        stock_price: Current stock price
        expiration: Option expiration date
        dte: Days to expiration
        config: Screener configuration

    Returns:
        List of qualifying CreditSpread objects
    """
    if puts.is_empty():
        return []

    # Filter for OTM puts (strike below current price)
    otm_puts = puts.filter(pl.col("strike") < stock_price)

    if otm_puts.is_empty():
        return []

    # Filter by delta range if delta is available
    delta_min, delta_max = config.target_delta_short

    # Check if delta column has non-null values
    has_delta = (
        "delta" in otm_puts.columns
        and otm_puts.select(pl.col("delta").is_not_null().any()).item()
    )

    if has_delta:
        short_candidates = otm_puts.filter(
            (pl.col("delta").abs().is_between(delta_min, delta_max))
            & (pl.col("open_interest") >= config.min_open_interest)
        )
    else:
        # If no delta, filter by distance from price (rough proxy)
        # Target roughly 15-30% OTM as a proxy for 0.20-0.35 delta
        short_candidates = otm_puts.filter(
            (pl.col("strike") >= stock_price * 0.85)
            & (pl.col("strike") <= stock_price * 0.95)
            & (pl.col("open_interest") >= config.min_open_interest)
        )

    if short_candidates.is_empty():
        return []

    spreads = []

    for short_row in short_candidates.iter_rows(named=True):
        short_strike = short_row["strike"]
        long_strike = short_strike - config.spread_width

        # Find the long leg
        long_candidates = puts.filter(pl.col("strike") == long_strike)

        if long_candidates.is_empty():
            # Try to find closest strike below
            below_strikes = puts.filter(
                (pl.col("strike") < short_strike)
                & (pl.col("strike") >= short_strike - config.spread_width - 2.5)
            ).sort("strike", descending=True)

            if below_strikes.is_empty():
                continue

            long_candidates = below_strikes.head(1)

        long_row = long_candidates.row(0, named=True)
        actual_width = short_strike - long_row["strike"]

        # Calculate premiums (midpoint of bid/ask)
        short_premium = (short_row["bid"] + short_row["ask"]) / 2
        long_premium = (long_row["bid"] + long_row["ask"]) / 2

        # Skip if premiums are invalid
        if short_premium <= 0 or long_premium < 0:
            continue

        net_credit = short_premium - long_premium
        max_loss = (actual_width - net_credit) * 100  # Per contract
        max_profit = net_credit * 100  # Per contract

        # Skip if no profit potential
        if net_credit <= 0 or max_loss <= 0:
            continue

        return_on_risk = (net_credit / (actual_width - net_credit)) * 100
        break_even = short_strike - net_credit
        distance_from_price = stock_price - short_strike

        # Apply filters
        if (
            net_credit >= config.min_credit
            and max_loss <= config.max_loss
            and return_on_risk >= config.min_return_on_risk
        ):
            spread = CreditSpread(
                ticker=ticker,
                spread_type=SPREAD_TYPE_BULL_PUT,
                expiration=expiration,
                days_to_expiration=dte,
                short_leg=create_option_leg(short_row),
                long_leg=create_option_leg(long_row),
                net_credit=round(net_credit, 2),
                max_loss=round(max_loss, 2),
                max_profit=round(max_profit, 2),
                return_on_risk=round(return_on_risk, 2),
                break_even=round(break_even, 2),
                width=actual_width,
                current_stock_price=round(stock_price, 2),
                distance_from_price=round(distance_from_price, 2),
            )
            spreads.append(spread)

    return spreads


def screen_bear_call_spreads(
    calls: pl.DataFrame,
    ticker: str,
    stock_price: float,
    expiration: date,
    dte: int,
    config: ScreenerConfig,
) -> list[CreditSpread]:
    """
    Screen for bear call spreads (bearish strategy).

    A bear call spread involves:
    - Selling a call at a lower strike (short leg)
    - Buying a call at a higher strike (long leg)
    - Net credit received upfront
    - Profitable when stock stays below short strike

    Args:
        calls: DataFrame of call options
        ticker: Stock ticker symbol
        stock_price: Current stock price
        expiration: Option expiration date
        dte: Days to expiration
        config: Screener configuration

    Returns:
        List of qualifying CreditSpread objects
    """
    if calls.is_empty():
        return []

    # Filter for OTM calls (strike above current price)
    otm_calls = calls.filter(pl.col("strike") > stock_price)

    if otm_calls.is_empty():
        return []

    # Filter by delta range if delta is available
    delta_min, delta_max = config.target_delta_short

    # Check if delta column has non-null values
    has_delta = (
        "delta" in otm_calls.columns
        and otm_calls.select(pl.col("delta").is_not_null().any()).item()
    )

    if has_delta:
        short_candidates = otm_calls.filter(
            (pl.col("delta").abs().is_between(delta_min, delta_max))
            & (pl.col("open_interest") >= config.min_open_interest)
        )
    else:
        # If no delta, filter by distance from price (rough proxy)
        # Target roughly 5-15% OTM as a proxy for 0.20-0.35 delta
        short_candidates = otm_calls.filter(
            (pl.col("strike") >= stock_price * 1.05)
            & (pl.col("strike") <= stock_price * 1.15)
            & (pl.col("open_interest") >= config.min_open_interest)
        )

    if short_candidates.is_empty():
        return []

    spreads = []

    for short_row in short_candidates.iter_rows(named=True):
        short_strike = short_row["strike"]
        long_strike = short_strike + config.spread_width

        # Find the long leg
        long_candidates = calls.filter(pl.col("strike") == long_strike)

        if long_candidates.is_empty():
            # Try to find closest strike above
            above_strikes = calls.filter(
                (pl.col("strike") > short_strike)
                & (pl.col("strike") <= short_strike + config.spread_width + 2.5)
            ).sort("strike")

            if above_strikes.is_empty():
                continue

            long_candidates = above_strikes.head(1)

        long_row = long_candidates.row(0, named=True)
        actual_width = long_row["strike"] - short_strike

        # Calculate premiums (midpoint of bid/ask)
        short_premium = (short_row["bid"] + short_row["ask"]) / 2
        long_premium = (long_row["bid"] + long_row["ask"]) / 2

        # Skip if premiums are invalid
        if short_premium <= 0 or long_premium < 0:
            continue

        net_credit = short_premium - long_premium
        max_loss = (actual_width - net_credit) * 100  # Per contract
        max_profit = net_credit * 100  # Per contract

        # Skip if no profit potential
        if net_credit <= 0 or max_loss <= 0:
            continue

        return_on_risk = (net_credit / (actual_width - net_credit)) * 100
        break_even = short_strike + net_credit
        distance_from_price = short_strike - stock_price

        # Apply filters
        if (
            net_credit >= config.min_credit
            and max_loss <= config.max_loss
            and return_on_risk >= config.min_return_on_risk
        ):
            spread = CreditSpread(
                ticker=ticker,
                spread_type=SPREAD_TYPE_BEAR_CALL,
                expiration=expiration,
                days_to_expiration=dte,
                short_leg=create_option_leg(short_row),
                long_leg=create_option_leg(long_row),
                net_credit=round(net_credit, 2),
                max_loss=round(max_loss, 2),
                max_profit=round(max_profit, 2),
                return_on_risk=round(return_on_risk, 2),
                break_even=round(break_even, 2),
                width=actual_width,
                current_stock_price=round(stock_price, 2),
                distance_from_price=round(distance_from_price, 2),
            )
            spreads.append(spread)

    return spreads


def screen_all_spreads(
    calls: pl.DataFrame,
    puts: pl.DataFrame,
    ticker: str,
    stock_price: float,
    expiration: date,
    dte: int,
    config: ScreenerConfig,
) -> list[CreditSpread]:
    """
    Screen for both bull put and bear call spreads.

    Args:
        calls: DataFrame of call options
        puts: DataFrame of put options
        ticker: Stock ticker symbol
        stock_price: Current stock price
        expiration: Option expiration date
        dte: Days to expiration
        config: Screener configuration

    Returns:
        Combined list of all qualifying spreads
    """
    bull_puts = screen_bull_put_spreads(
        puts, ticker, stock_price, expiration, dte, config
    )
    bear_calls = screen_bear_call_spreads(
        calls, ticker, stock_price, expiration, dte, config
    )

    return bull_puts + bear_calls


def rank_spreads(spreads: list[CreditSpread]) -> list[CreditSpread]:
    """
    Rank spreads by quality score.

    Scoring factors:
    - Higher return on risk is better
    - Higher distance from price (safety buffer) is better
    - Better liquidity (higher OI) is better

    Args:
        spreads: List of credit spreads to rank

    Returns:
        Sorted list of spreads by quality score (best first)
    """
    if not spreads:
        return spreads

    def quality_score(spread: CreditSpread) -> float:
        # Normalize return on risk (0-100 range expected)
        ror_score = spread.return_on_risk / 100

        # Normalize distance from price as percentage
        distance_pct = spread.distance_from_price_pct / 100

        # Normalize open interest (log scale, cap at 10000)
        oi = min(spread.short_leg.open_interest, 10000)
        oi_score = (oi / 10000) ** 0.5  # Square root to compress range

        # Weighted combination
        return (ror_score * 0.5) + (distance_pct * 0.3) + (oi_score * 0.2)

    return sorted(spreads, key=quality_score, reverse=True)


def filter_duplicate_strikes(spreads: list[CreditSpread]) -> list[CreditSpread]:
    """
    Remove duplicate spreads that have the same ticker/type/strikes.

    Keeps the one with better return on risk.

    Args:
        spreads: List of credit spreads

    Returns:
        Deduplicated list of spreads
    """
    seen = {}

    for spread in spreads:
        key = (
            spread.ticker,
            spread.spread_type,
            spread.short_leg.strike,
            spread.long_leg.strike,
            spread.expiration,
        )

        if key not in seen or spread.return_on_risk > seen[key].return_on_risk:
            seen[key] = spread

    return list(seen.values())
