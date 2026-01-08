"""yfinance wrapper for fetching options chain data."""

import time
from datetime import datetime, date
from functools import lru_cache
from typing import NamedTuple

import polars as pl
import yfinance as yf


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

        # Fetch options chain
        chain = stock.option_chain(expiration)

        # Convert to Polars DataFrames with standardized column names
        calls_df = self._convert_options_df(chain.calls, "call")
        puts_df = self._convert_options_df(chain.puts, "put")

        exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()

        return OptionsChain(
            calls=calls_df,
            puts=puts_df,
            expiration=exp_date,
            stock_price=price,
        )

    def _convert_options_df(self, pandas_df, option_type: str) -> pl.DataFrame:
        """
        Convert pandas options DataFrame to Polars with standardized columns.

        Args:
            pandas_df: pandas DataFrame from yfinance
            option_type: "call" or "put"

        Returns:
            Polars DataFrame with standardized columns
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

        # Ensure required columns exist with defaults
        if "delta" not in df.columns:
            df = df.with_columns(pl.lit(None).alias("delta").cast(pl.Float64))

        if "gamma" not in df.columns:
            df = df.with_columns(pl.lit(None).alias("gamma").cast(pl.Float64))

        if "theta" not in df.columns:
            df = df.with_columns(pl.lit(None).alias("theta").cast(pl.Float64))

        if "vega" not in df.columns:
            df = df.with_columns(pl.lit(None).alias("vega").cast(pl.Float64))

        # Add option type column
        df = df.with_columns(pl.lit(option_type).alias("option_type"))

        # Calculate midpoint premium
        df = df.with_columns(
            ((pl.col("bid") + pl.col("ask")) / 2).alias("premium")
        )

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
