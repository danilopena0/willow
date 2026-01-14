"""Centralized constants for the options screener."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScreeningDefaults:
    """Default values for screening parameters."""

    MAX_PARALLEL_WORKERS: int = 5
    STRIKE_WIDTH_TOLERANCE: float = 1.0
    RATE_LIMIT_DELAY: float = 0.3
    MAX_RETRIES: int = 3
    CACHE_EXPIRE_SECONDS: int = 300  # 5 minutes


@dataclass(frozen=True)
class QualityScoreWeights:
    """
    Weights for calculating spread quality score.

    The quality score ranks spreads by combining multiple factors:

    ROR (Return on Risk): The percentage profit relative to max loss.
        Higher ROR = more profit per dollar risked. Weighted highest because
        it directly measures the trade's efficiency.

    POP (Probability of Profit): Derived from short leg delta (1 - |delta|).
        Represents the statistical likelihood the spread expires worthless
        (profitable). A 0.30 delta short = ~70% POP.

    DISTANCE: How far OTM the short strike is from current price (as %).
        Greater distance = larger safety buffer before the trade goes ITM.
        Provides margin for error if the stock moves against you.

    OPEN_INTEREST: Number of outstanding contracts at the strike.
        Higher OI = better liquidity, tighter bid-ask spreads, easier
        to enter/exit positions at fair prices.
    """

    ROR: float = 0.35           # Return on Risk - trade efficiency
    POP: float = 0.25           # Probability of Profit - win rate
    DISTANCE: float = 0.25      # Distance from price - safety margin
    OPEN_INTEREST: float = 0.15 # Liquidity indicator


@dataclass(frozen=True)
class VIXLevels:
    """VIX threshold levels for market context."""

    LOW: float = 15.0
    NORMAL: float = 20.0
    ELEVATED: float = 30.0


@dataclass(frozen=True)
class ExcelFormatThresholds:
    """Thresholds for Excel conditional formatting color scales."""

    # ROR % thresholds (red -> yellow -> green)
    ROR_MIN: float = 0.15
    ROR_MID: float = 0.25
    ROR_MAX: float = 0.40

    # Annualized % thresholds
    ANNUALIZED_MIN: float = 1.0
    ANNUALIZED_MID: float = 2.0
    ANNUALIZED_MAX: float = 4.0

    # POP % thresholds
    POP_MIN: float = 0.60
    POP_MID: float = 0.70
    POP_MAX: float = 0.80

    # DTE thresholds
    DTE_MIN: int = 14
    DTE_MID: int = 37
    DTE_MAX: int = 60

    # Distance % thresholds
    DISTANCE_MIN: float = 0.01
    DISTANCE_MID: float = 0.05
    DISTANCE_MAX: float = 0.10


# Singleton instances for easy import
SCREENING = ScreeningDefaults()
QUALITY_WEIGHTS = QualityScoreWeights()
VIX = VIXLevels()
EXCEL_FORMAT = ExcelFormatThresholds()
