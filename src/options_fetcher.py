"""yfinance wrapper for fetching options chain data."""

import math
import time
from datetime import datetime, date
from functools import lru_cache
from typing import NamedTuple

import numpy as np
import polars as pl
import yfinance as yf
from scipy.stats import norm


# Default risk-free rate (approximate current US Treasury rate)
RISK_FREE_RATE = 0.045


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


class OptionsFetcher:
    """Wrapper for yfinance options data fetching with caching and rate limiting."""

    def __init__(self, rate_limit_delay: float = 0.5):
        """
        Initialize the options fetcher.

        Args:
            rate_limit_delay: Seconds to wait between API calls to avoid rate limiting
        """
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time = 0.0
        self._ticker_cache: dict[str, yf.Ticker] = {}

    def _rate_limit(self) -> None:
        """Enforce rate limiting between API calls."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

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
        self._rate_limit()
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
        Fetch options chain for a specific expiration.

        Args:
            ticker: Stock ticker symbol
            expiration: Expiration date string (YYYY-MM-DD)

        Returns:
            OptionsChain containing calls and puts DataFrames
        """
        self._rate_limit()
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
        self._rate_limit()
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
        self._rate_limit()
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


# Module-level convenience functions
_default_fetcher: OptionsFetcher | None = None


def get_fetcher() -> OptionsFetcher:
    """Get the default options fetcher instance."""
    global _default_fetcher
    if _default_fetcher is None:
        _default_fetcher = OptionsFetcher()
    return _default_fetcher


def fetch_options_chain(ticker: str, expiration: str) -> OptionsChain:
    """Convenience function to fetch options chain."""
    return get_fetcher().fetch_options_chain(ticker, expiration)


def get_expirations(ticker: str) -> list[str]:
    """Convenience function to get expiration dates."""
    return get_fetcher().get_expirations(ticker)


def get_stock_price(ticker: str) -> float:
    """Convenience function to get stock price."""
    return get_fetcher().get_stock_price(ticker)
