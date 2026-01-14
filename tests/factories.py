"""Test factories for creating test objects with sensible defaults."""

from datetime import date, timedelta

from src.models import CreditSpread, OptionLeg, ScreenerConfig


def create_option_leg(
    strike: float = 100.0,
    premium: float = 1.50,
    bid: float = 1.45,
    ask: float = 1.55,
    delta: float = 0.30,
    implied_volatility: float = 0.25,
    open_interest: int = 500,
    volume: int = 100,
    contract_symbol: str | None = None,
    **overrides,
) -> OptionLeg:
    """
    Create an OptionLeg with sensible defaults.

    All parameters can be overridden via kwargs.
    """
    return OptionLeg(
        strike=overrides.get("strike", strike),
        premium=overrides.get("premium", premium),
        bid=overrides.get("bid", bid),
        ask=overrides.get("ask", ask),
        delta=overrides.get("delta", delta),
        implied_volatility=overrides.get("implied_volatility", implied_volatility),
        open_interest=overrides.get("open_interest", open_interest),
        volume=overrides.get("volume", volume),
        contract_symbol=overrides.get("contract_symbol", contract_symbol),
    )


def create_credit_spread(
    ticker: str = "SPY",
    spread_type: str = "bull_put",
    expiration: date | None = None,
    days_to_expiration: int = 30,
    short_leg: OptionLeg | None = None,
    long_leg: OptionLeg | None = None,
    net_credit: float = 0.50,
    max_loss: float = 450.0,
    max_profit: float = 50.0,
    return_on_risk: float = 25.0,
    break_even: float = 99.50,
    width: float = 5.0,
    current_stock_price: float = 105.0,
    distance_from_price: float = 5.0,
    probability_of_profit: float = 70.0,
    **overrides,
) -> CreditSpread:
    """
    Create a CreditSpread with sensible defaults.

    Creates realistic short/long legs if not provided.
    All parameters can be overridden via kwargs.
    """
    if expiration is None:
        expiration = date.today() + timedelta(days=days_to_expiration)

    if short_leg is None:
        short_leg = create_option_leg(
            strike=100.0,
            premium=1.50,
            bid=1.45,
            ask=1.55,
            delta=0.30,
            open_interest=500,
        )

    if long_leg is None:
        long_leg = create_option_leg(
            strike=95.0,
            premium=1.00,
            bid=0.95,
            ask=1.05,
            delta=0.20,
            open_interest=300,
        )

    return CreditSpread(
        ticker=overrides.get("ticker", ticker),
        spread_type=overrides.get("spread_type", spread_type),
        expiration=overrides.get("expiration", expiration),
        days_to_expiration=overrides.get("days_to_expiration", days_to_expiration),
        short_leg=overrides.get("short_leg", short_leg),
        long_leg=overrides.get("long_leg", long_leg),
        net_credit=overrides.get("net_credit", net_credit),
        max_loss=overrides.get("max_loss", max_loss),
        max_profit=overrides.get("max_profit", max_profit),
        return_on_risk=overrides.get("return_on_risk", return_on_risk),
        break_even=overrides.get("break_even", break_even),
        width=overrides.get("width", width),
        current_stock_price=overrides.get("current_stock_price", current_stock_price),
        distance_from_price=overrides.get("distance_from_price", distance_from_price),
        probability_of_profit=overrides.get("probability_of_profit", probability_of_profit),
    )


def create_screener_config(
    tickers: list[str] | None = None,
    min_dte: int = 30,
    max_dte: int = 45,
    min_credit: float = 0.20,
    max_loss: float = 500.0,
    min_return_on_risk: float = 20.0,
    max_return_on_risk: float = 75.0,
    min_distance_pct: float = 5.0,
    target_delta_short: tuple[float, float] = (0.20, 0.35),
    min_open_interest: int = 50,
    spread_widths: list[int] | None = None,
    **overrides,
) -> ScreenerConfig:
    """
    Create a ScreenerConfig with sensible defaults.

    All parameters can be overridden via kwargs.
    """
    return ScreenerConfig(
        tickers=overrides.get("tickers", tickers or ["SPY", "QQQ"]),
        min_dte=overrides.get("min_dte", min_dte),
        max_dte=overrides.get("max_dte", max_dte),
        min_credit=overrides.get("min_credit", min_credit),
        max_loss=overrides.get("max_loss", max_loss),
        min_return_on_risk=overrides.get("min_return_on_risk", min_return_on_risk),
        max_return_on_risk=overrides.get("max_return_on_risk", max_return_on_risk),
        min_distance_pct=overrides.get("min_distance_pct", min_distance_pct),
        target_delta_short=overrides.get("target_delta_short", target_delta_short),
        min_open_interest=overrides.get("min_open_interest", min_open_interest),
        spread_widths=overrides.get("spread_widths", spread_widths or [1, 2, 5]),
    )


def create_spread_list(count: int = 5, **spread_kwargs) -> list[CreditSpread]:
    """
    Create a list of CreditSpreads with varying parameters.

    Args:
        count: Number of spreads to create
        **spread_kwargs: Base kwargs passed to each spread

    Returns:
        List of CreditSpread objects with varied tickers and ROR
    """
    tickers = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"]
    spreads = []

    for i in range(count):
        spread = create_credit_spread(
            ticker=tickers[i % len(tickers)],
            return_on_risk=20.0 + (i * 5),  # Vary ROR: 20, 25, 30, ...
            probability_of_profit=65.0 + (i * 2),  # Vary POP: 65, 67, 69, ...
            **spread_kwargs,
        )
        spreads.append(spread)

    return spreads
