"""Pydantic models for options credit spread screening."""

from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator, computed_field


class OptionLeg(BaseModel):
    """Represents a single option leg in a spread."""

    strike: float
    premium: float  # midpoint of bid/ask
    bid: float
    ask: float
    delta: float | None = None
    implied_volatility: float | None = None
    open_interest: int = 0
    volume: int = 0
    contract_symbol: str | None = None

    @field_validator("delta", mode="before")
    @classmethod
    def normalize_delta(cls, v: float | None) -> float | None:
        """Ensure delta is stored as absolute value for puts."""
        if v is None:
            return None
        return abs(v) if v < 0 else v

    @computed_field
    @property
    def spread_percentage(self) -> float:
        """Calculate bid-ask spread as percentage of midpoint."""
        if self.premium == 0:
            return 0.0
        return ((self.ask - self.bid) / self.premium) * 100


class CreditSpread(BaseModel):
    """Represents a credit spread opportunity."""

    ticker: str
    spread_type: str  # "bull_put" or "bear_call"
    expiration: date
    days_to_expiration: int
    short_leg: OptionLeg
    long_leg: OptionLeg
    net_credit: float
    max_loss: float
    max_profit: float
    return_on_risk: float  # percentage
    break_even: float
    width: float
    current_stock_price: float
    distance_from_price: float  # short strike distance from current price
    probability_of_profit: float  # estimated POP based on delta
    timestamp: datetime = Field(default_factory=datetime.now)

    @computed_field
    @property
    def annualized_return(self) -> float:
        """Annualized return on risk (ROR * 365 / DTE)."""
        if self.days_to_expiration == 0:
            return 0.0
        return round(self.return_on_risk * (365 / self.days_to_expiration), 2)

    @computed_field
    @property
    def distance_from_price_pct(self) -> float:
        """Distance from current price as percentage."""
        if self.current_stock_price == 0:
            return 0.0
        return (self.distance_from_price / self.current_stock_price) * 100

    @computed_field
    @property
    def risk_reward_ratio(self) -> float:
        """Risk to reward ratio (lower is better)."""
        if self.max_profit == 0:
            return float("inf")
        return self.max_loss / self.max_profit

    def to_summary(self) -> str:
        """Return a human-readable summary of the spread."""
        return (
            f"{self.ticker} {self.spread_type.replace('_', ' ').title()}: "
            f"${self.short_leg.strike:.0f}/${self.long_leg.strike:.0f} "
            f"Credit: ${self.net_credit:.2f} | ROR: {self.return_on_risk:.1f}% | "
            f"DTE: {self.days_to_expiration}"
        )


class ScreenerConfig(BaseModel):
    """Configuration for the options screener."""

    tickers: list[str] = Field(
        default_factory=lambda: ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD"]
    )
    min_dte: int = Field(default=30, description="Minimum days to expiration")
    max_dte: int = Field(default=45, description="Maximum days to expiration")
    min_credit: float = Field(default=0.20, description="Minimum net credit per spread")
    max_loss: float = Field(default=500.0, description="Maximum loss per spread")
    min_return_on_risk: float = Field(default=20.0, description="Minimum return on risk percentage")
    target_delta_short: tuple[float, float] = Field(
        default=(0.20, 0.35),
        description="Target delta range for short leg"
    )
    min_open_interest: int = Field(default=50, description="Minimum open interest for liquidity")
    spread_widths: list[int] = Field(default_factory=lambda: [1, 2, 5], description="Widths between strikes to scan")
    earnings_buffer_days: int = Field(default=0, description="Skip tickers with earnings within N days (0 = disabled)")
    alert_threshold_ror: float = Field(default=30.0, description="Alert if ROR exceeds this")

    # Alert settings
    enable_slack_alerts: bool = False

    @field_validator("tickers", mode="before")
    @classmethod
    def uppercase_tickers(cls, v: list[str]) -> list[str]:
        """Ensure all tickers are uppercase."""
        return [t.upper() for t in v]

    @field_validator("target_delta_short", mode="before")
    @classmethod
    def validate_delta_range(cls, v: tuple[float, float]) -> tuple[float, float]:
        """Ensure delta range is valid."""
        if isinstance(v, (list, tuple)) and len(v) == 2:
            low, high = v
            if not (0 < low < high < 1):
                raise ValueError("Delta range must be between 0 and 1, with low < high")
            return (low, high)
        raise ValueError("target_delta_short must be a tuple of (low, high)")


class AlertConfig(BaseModel):
    """Configuration for alert system."""

    # Slack webhook settings
    slack_webhook_url: str | None = None

    @computed_field
    @property
    def slack_configured(self) -> bool:
        """Check if Slack alerts are properly configured."""
        return self.slack_webhook_url is not None


class ScreenerResult(BaseModel):
    """Results from a screening run."""

    timestamp: datetime
    config: ScreenerConfig
    spreads: list[CreditSpread]
    tickers_screened: int
    tickers_with_errors: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def total_spreads(self) -> int:
        """Total number of spreads found."""
        return len(self.spreads)

    @computed_field
    @property
    def avg_return_on_risk(self) -> float:
        """Average return on risk across all spreads."""
        if not self.spreads:
            return 0.0
        return sum(s.return_on_risk for s in self.spreads) / len(self.spreads)

    @computed_field
    @property
    def bull_put_count(self) -> int:
        """Number of bull put spreads found."""
        return sum(1 for s in self.spreads if s.spread_type == "bull_put")

    @computed_field
    @property
    def bear_call_count(self) -> int:
        """Number of bear call spreads found."""
        return sum(1 for s in self.spreads if s.spread_type == "bear_call")
