"""yfinance wrapper for fetching options chain data."""

import math
import time
from datetime import datetime, date
from pathlib import Path
from typing import Callable, NamedTuple, TypeVar

import numpy as np
import polars as pl
import yfinance as yf
from diskcache import Cache
from scipy.stats import norm


# Type variable for generic return type
T = TypeVar('T')

# Default risk-free rate (approximate current US Treasury rate)
RISK_FREE_RATE = 0.045

# Cache configuration
CACHE_DIR = Path(__file__).parent.parent / "data" / ".cache"
CACHE_EXPIRE_SECONDS = 300  # 5 minutes


def calculate_bs_delta(
    stock_price: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    risk_free_rate: float = RISK_FREE_RATE,
    option_type: str = "call",
) -> float:
    """
    Calculate option delta using Black-Scholes model.

    Args:
        stock_price: Current stock price
        strike: Option strike price
        time_to_expiry: Time to expiration in years
        volatility: Implied volatility (as decimal, e.g., 0.25 for 25%)
        risk_free_rate: Risk-free interest rate (default 4.5%)
        option_type: "call" or "put"

    Returns:
        Delta value (0 to 1 for calls, -1 to 0 for puts)
    """
    if time_to_expiry <= 0 or volatility <= 0 or stock_price <= 0 or strike <= 0:
        return 0.0

    try:
        d1 = (
            math.log(stock_price / strike)
            + (risk_free_rate + 0.5 * volatility**2) * time_to_expiry
        ) / (volatility * math.sqrt(time_to_expiry))

        if option_type == "call":
            return norm.cdf(d1)
        else:  # put
            return norm.cdf(d1) - 1
    except (ValueError, ZeroDivisionError):
        return 0.0


class OptionsChain(NamedTuple):
    """Container for options chain data."""
    calls: pl.DataFrame
    puts: pl.DataFrame
    expiration: date
    stock_price: float


class TickerData(NamedTuple):
    """Container for ticker market data."""
    price: float
    price_history: pl.DataFrame


class RateLimiter:
    """Enforces minimum delay between API calls to avoid rate limiting."""

    def __init__(self, delay: float = 0.3):
        """
        Args:
            delay: Minimum seconds between calls
        """
        self.delay = delay
        self._last_request_time = 0.0

    def wait(self) -> None:
        """Wait if needed to respect rate limit."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()


class RetryHandler:
    """Executes functions with exponential backoff retry on failure."""

    def __init__(self, max_retries: int = 3):
        """
        Args:
            max_retries: Maximum number of attempts before giving up
        """
        self.max_retries = max_retries

    def execute(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute function with retry logic.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result of func

        Raises:
            Exception: If all retries fail
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s...
                    time.sleep(wait_time)

        raise last_exception


class OptionsFetcher:
    """Wrapper for yfinance options data fetching with caching, rate limiting, and retry."""

    def __init__(
        self,
        rate_limiter: RateLimiter | None = None,
        retry_handler: RetryHandler | None = None,
        use_cache: bool = True,
    ):
        """
        Initialize the options fetcher.

        Args:
            rate_limiter: Rate limiter instance (created with defaults if not provided)
            retry_handler: Retry handler instance (created with defaults if not provided)
            use_cache: Whether to use disk caching for API responses
        """
        self._rate_limiter = rate_limiter or RateLimiter()
        self._retry_handler = retry_handler or RetryHandler()
        self._ticker_cache: dict[str, yf.Ticker] = {}

        # Initialize disk cache
        if use_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._cache = Cache(str(CACHE_DIR))
        else:
            self._cache = None

    def _get_ticker(self, symbol: str) -> yf.Ticker:
        """Get a cached ticker object."""
        if symbol not in self._ticker_cache:
            self._ticker_cache[symbol] = yf.Ticker(symbol)
        return self._ticker_cache[symbol]

    def get_expirations(self, ticker: str) -> list[str]:
        """
        Get available expiration dates for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            List of expiration dates as strings (YYYY-MM-DD format)
        """
        self._rate_limiter.wait()
        stock = self._get_ticker(ticker)
        return list(stock.options)

    def get_expirations_in_range(
        self, ticker: str, min_dte: int, max_dte: int
    ) -> list[tuple[str, int]]:
        """
        Get expiration dates within a DTE range.

        Args:
            ticker: Stock ticker symbol
            min_dte: Minimum days to expiration
            max_dte: Maximum days to expiration

        Returns:
            List of (expiration_date, days_to_expiration) tuples
        """
        expirations = self.get_expirations(ticker)
        today = datetime.now().date()
        result = []

        for exp_str in expirations:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            dte = (exp_date - today).days

            if min_dte <= dte <= max_dte:
                result.append((exp_str, dte))

        return result

    def fetch_options_chain(self, ticker: str, expiration: str) -> OptionsChain:
        """
        Fetch options chain for a specific expiration with caching and retry.

        Args:
            ticker: Stock ticker symbol
            expiration: Expiration date string (YYYY-MM-DD)

        Returns:
            OptionsChain containing calls and puts DataFrames
        """
        cache_key = f"chain:{ticker}:{expiration}"

        # Check cache first
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        self._rate_limiter.wait()

        def _fetch():
            stock = self._get_ticker(ticker)

            # Get current stock price
            info = stock.info
            price = info.get("regularMarketPrice") or info.get("currentPrice", 0.0)

            # Calculate days to expiry
            exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
            days_to_expiry = (exp_date - datetime.now().date()).days

            # Fetch options chain
            chain = stock.option_chain(expiration)

            # Convert to Polars DataFrames with standardized column names and calculated delta
            calls_df = self._convert_options_df(chain.calls, "call", price, days_to_expiry)
            puts_df = self._convert_options_df(chain.puts, "put", price, days_to_expiry)

            return OptionsChain(
                calls=calls_df,
                puts=puts_df,
                expiration=exp_date,
                stock_price=price,
            )

        result = self._retry_handler.execute(_fetch)

        # Cache the result
        if self._cache is not None:
            self._cache.set(cache_key, result, expire=CACHE_EXPIRE_SECONDS)

        return result

    def _convert_options_df(
        self,
        pandas_df,
        option_type: str,
        stock_price: float,
        days_to_expiry: int,
    ) -> pl.DataFrame:
        """
        Convert pandas options DataFrame to Polars with standardized columns.
        Calculates Black-Scholes delta if not provided by yfinance.

        Args:
            pandas_df: pandas DataFrame from yfinance
            option_type: "call" or "put"
            stock_price: Current stock price for delta calculation
            days_to_expiry: Days to expiration for delta calculation

        Returns:
            Polars DataFrame with standardized columns including calculated delta
        """
        if pandas_df.empty:
            return pl.DataFrame()

        df = pl.from_pandas(pandas_df)

        # Standardize column names and handle missing columns
        column_mapping = {
            "contractSymbol": "contract_symbol",
            "lastTradeDate": "last_trade_date",
            "lastPrice": "last_price",
            "openInterest": "open_interest",
            "impliedVolatility": "implied_volatility",
            "inTheMoney": "in_the_money",
        }

        # Rename columns that exist
        for old_name, new_name in column_mapping.items():
            if old_name in df.columns:
                df = df.rename({old_name: new_name})

        # Add option type column
        df = df.with_columns(pl.lit(option_type).alias("option_type"))

        # Calculate midpoint premium
        df = df.with_columns(
            ((pl.col("bid") + pl.col("ask")) / 2).alias("premium")
        )

        # Calculate Black-Scholes delta if not provided
        time_to_expiry = days_to_expiry / 365.0

        if "delta" not in df.columns or df.select(pl.col("delta").is_null().all()).item():
            # Calculate delta for each row using Black-Scholes
            deltas = []
            for row in df.iter_rows(named=True):
                iv = row.get("implied_volatility", 0) or 0
                strike = row.get("strike", 0) or 0

                if iv > 0 and strike > 0 and stock_price > 0:
                    delta = calculate_bs_delta(
                        stock_price=stock_price,
                        strike=strike,
                        time_to_expiry=time_to_expiry,
                        volatility=iv,
                        option_type=option_type,
                    )
                else:
                    delta = None

                deltas.append(delta)

            df = df.with_columns(pl.Series("delta", deltas).cast(pl.Float64))

        return df

    def get_stock_price(self, ticker: str) -> float:
        """
        Get current stock price for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Current stock price
        """
        self._rate_limiter.wait()
        stock = self._get_ticker(ticker)
        info = stock.info
        return info.get("regularMarketPrice") or info.get("currentPrice", 0.0)

    def get_price_history(
        self, ticker: str, period: str = "3mo", interval: str = "1d"
    ) -> pl.DataFrame:
        """
        Get historical price data for a ticker.

        Args:
            ticker: Stock ticker symbol
            period: Time period (e.g., "1mo", "3mo", "1y")
            interval: Data interval (e.g., "1d", "1h")

        Returns:
            Polars DataFrame with OHLCV data
        """
        self._rate_limiter.wait()
        stock = self._get_ticker(ticker)
        hist = stock.history(period=period, interval=interval)

        if hist.empty:
            return pl.DataFrame()

        # Convert to Polars
        df = pl.from_pandas(hist.reset_index())

        # Standardize column names
        df = df.rename({
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })

        return df.select(["date", "open", "high", "low", "close", "volume"])

    def get_ticker_data(self, ticker: str, history_period: str = "3mo") -> TickerData:
        """
        Get comprehensive ticker data including price and history.

        Args:
            ticker: Stock ticker symbol
            history_period: Period for price history

        Returns:
            TickerData with price and history
        """
        price = self.get_stock_price(ticker)
        history = self.get_price_history(ticker, period=history_period)
        return TickerData(price=price, price_history=history)

    def get_next_earnings_date(self, ticker: str) -> date | None:
        """
        Get the next earnings date for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Next earnings date, or None if not available (including ETFs)
        """
        import io
        import sys
        import logging

        # Suppress yfinance HTTP error logging temporarily
        yf_logger = logging.getLogger('yfinance')
        original_level = yf_logger.level
        yf_logger.setLevel(logging.CRITICAL)

        # Capture stdout/stderr to suppress HTTP error messages from urllib
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()

        try:
            stock = self._get_ticker(ticker)

            try:
                calendar = stock.calendar
            except Exception:
                # ETFs and some tickers don't have calendar data - this is expected
                return None

            if calendar is None:
                return None

            # Handle empty DataFrame
            if hasattr(calendar, 'empty') and calendar.empty:
                return None

            # yfinance returns calendar as DataFrame with 'Earnings Date' row
            # or as dict with 'Earnings Date' key depending on version
            if isinstance(calendar, dict):
                earnings = calendar.get("Earnings Date")
                if not earnings:
                    return None

                # Can be a list of dates or single date
                if isinstance(earnings, list) and len(earnings) > 0:
                    first_date = earnings[0]
                    if hasattr(first_date, 'date'):
                        return first_date.date()
                    elif isinstance(first_date, date):
                        return first_date
                    else:
                        # Try to parse string
                        return datetime.strptime(str(first_date), "%Y-%m-%d").date()
                elif hasattr(earnings, 'date'):
                    return earnings.date()
                elif isinstance(earnings, date):
                    return earnings

            else:
                # DataFrame format (older yfinance versions)
                if "Earnings Date" in calendar.index:
                    earnings_val = calendar.loc["Earnings Date"].iloc[0]
                    if hasattr(earnings_val, 'date'):
                        return earnings_val.date()
                    elif isinstance(earnings_val, date):
                        return earnings_val
                    elif earnings_val is not None:
                        return datetime.strptime(str(earnings_val), "%Y-%m-%d").date()

            return None

        except AttributeError:
            # Calendar structure different than expected
            return None
        except KeyError:
            # Earnings Date key not found
            return None
        except ValueError:
            # Date parsing failed
            return None
        except Exception:
            # Catch-all for unexpected errors - silent for ETFs etc
            return None
        finally:
            # Restore stdout, stderr and logger level
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            yf_logger.setLevel(original_level)

    def has_earnings_soon(self, ticker: str, buffer_days: int = 7) -> bool:
        """
        Check if a ticker has earnings within the specified buffer period.

        Args:
            ticker: Stock ticker symbol
            buffer_days: Number of days to check ahead

        Returns:
            True if earnings are within buffer_days
        """
        earnings_date = self.get_next_earnings_date(ticker)
        if earnings_date is None:
            return False

        today = datetime.now().date()
        days_until_earnings = (earnings_date - today).days

        return 0 <= days_until_earnings <= buffer_days

    def clear_cache(self) -> None:
        """Clear the ticker cache."""
        self._ticker_cache.clear()
