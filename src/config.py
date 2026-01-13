"""Configuration management for the options screener."""

import os
from pathlib import Path
from dotenv import load_dotenv

from src.models import ScreenerConfig, AlertConfig

# Load environment variables from .env file
load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = DATA_DIR / "results"
DASHBOARDS_DIR = DATA_DIR / "dashboards"
HISTORY_DIR = DATA_DIR / "history"
LOGS_DIR = PROJECT_ROOT / "logs"

# Ensure directories exist
for dir_path in [RESULTS_DIR, DASHBOARDS_DIR, HISTORY_DIR, LOGS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)


def load_config() -> ScreenerConfig:
    """Load screener configuration from environment or defaults."""
    tickers_env = os.getenv("SCREENER_TICKERS")
    tickers = tickers_env.split(",") if tickers_env else None

    # Parse spread widths from comma-separated string
    widths_env = os.getenv("SCREENER_SPREAD_WIDTHS", "1,2,5")
    spread_widths = [int(w.strip()) for w in widths_env.split(",")]

    return ScreenerConfig(
        tickers=tickers or ScreenerConfig.model_fields["tickers"].default_factory(),
        min_dte=int(os.getenv("SCREENER_MIN_DTE", "30")),
        max_dte=int(os.getenv("SCREENER_MAX_DTE", "45")),
        min_credit=float(os.getenv("SCREENER_MIN_CREDIT", "0.20")),
        max_loss=float(os.getenv("SCREENER_MAX_LOSS", "500")),
        min_return_on_risk=float(os.getenv("SCREENER_MIN_ROR", "20")),
        min_open_interest=int(os.getenv("SCREENER_MIN_OI", "50")),
        spread_widths=spread_widths,
        earnings_buffer_days=int(os.getenv("SCREENER_EARNINGS_BUFFER", "0")),
        alert_threshold_ror=float(os.getenv("SCREENER_ALERT_THRESHOLD", "30")),
        enable_slack_alerts=os.getenv("ENABLE_SLACK_ALERTS", "false").lower() == "true",
    )


def load_alert_config() -> AlertConfig:
    """Load alert configuration from environment variables."""
    return AlertConfig(
        slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
    )


# Default watchlist with common liquid tickers
DEFAULT_WATCHLIST = [
    # Major indices ETFs
    "SPY",   # S&P 500
    "QQQ",   # Nasdaq 100
    "IWM",   # Russell 2000
    "DIA",   # Dow Jones

    # Large cap tech
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "NVDA",
    "TSLA",

    # Semiconductors
    "AMD",
    "INTC",
    "MU",

    # Financials
    "JPM",
    "BAC",
    "GS",

    # Other high-volume tickers
    "XOM",
    "WMT",
    "DIS",
]


# Spread type constants
SPREAD_TYPE_BULL_PUT = "bull_put"
SPREAD_TYPE_BEAR_CALL = "bear_call"
