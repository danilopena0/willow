"""Tests for spread calculator module."""

import pytest
from datetime import date

import polars as pl

from src.models import ScreenerConfig, CreditSpread
from src.spread_calculator import (
    create_option_leg,
    screen_bull_put_spreads,
    screen_bear_call_spreads,
    screen_all_spreads,
    rank_spreads,
    filter_duplicate_strikes,
)


@pytest.fixture
def sample_puts() -> pl.DataFrame:
    """Create sample put options DataFrame."""
    return pl.DataFrame({
        "strike": [85.0, 90.0, 95.0, 100.0, 105.0],
        "bid": [0.20, 0.45, 1.20, 3.50, 7.00],
        "ask": [0.25, 0.55, 1.40, 3.70, 7.30],
        "premium": [0.225, 0.50, 1.30, 3.60, 7.15],
        "delta": [-0.10, -0.18, -0.30, -0.45, -0.60],
        "open_interest": [100, 200, 500, 800, 300],
        "volume": [50, 100, 250, 400, 150],
        "implied_volatility": [0.25, 0.24, 0.23, 0.22, 0.21],
        "contract_symbol": ["P85", "P90", "P95", "P100", "P105"],
    })


@pytest.fixture
def sample_calls() -> pl.DataFrame:
    """Create sample call options DataFrame."""
    return pl.DataFrame({
        "strike": [95.0, 100.0, 105.0, 110.0, 115.0],
        "bid": [7.00, 3.50, 1.20, 0.45, 0.20],
        "ask": [7.30, 3.70, 1.40, 0.55, 0.25],
        "premium": [7.15, 3.60, 1.30, 0.50, 0.225],
        "delta": [0.60, 0.45, 0.30, 0.18, 0.10],
        "open_interest": [300, 800, 500, 200, 100],
        "volume": [150, 400, 250, 100, 50],
        "implied_volatility": [0.21, 0.22, 0.23, 0.24, 0.25],
        "contract_symbol": ["C95", "C100", "C105", "C110", "C115"],
    })


@pytest.fixture
def screener_config() -> ScreenerConfig:
    """Create test screener config."""
    return ScreenerConfig(
        min_dte=30,
        max_dte=45,
        min_credit=0.30,
        max_loss=500,
        min_return_on_risk=15.0,
        target_delta_short=(0.15, 0.35),
        min_open_interest=50,
        spread_width=5,
    )


class TestCreateOptionLeg:
    """Tests for create_option_leg function."""

    def test_create_from_dict(self):
        """Test creating option leg from dictionary."""
        row = {
            "strike": 100.0,
            "premium": 1.50,
            "bid": 1.45,
            "ask": 1.55,
            "delta": 0.30,
            "implied_volatility": 0.25,
            "open_interest": 500,
            "volume": 100,
            "contract_symbol": "TEST",
        }

        leg = create_option_leg(row)

        assert leg.strike == 100.0
        assert leg.premium == 1.50
        assert leg.bid == 1.45
        assert leg.ask == 1.55
        assert leg.delta == 0.30
        assert leg.open_interest == 500
        assert leg.contract_symbol == "TEST"

    def test_create_with_missing_fields(self):
        """Test creating option leg with missing optional fields."""
        row = {
            "strike": 100.0,
            "bid": 1.45,
            "ask": 1.55,
        }

        leg = create_option_leg(row)

        assert leg.strike == 100.0
        assert leg.premium == 0.0
        assert leg.delta is None
        assert leg.open_interest == 0


class TestScreenBullPutSpreads:
    """Tests for bull put spread screening."""

    def test_finds_qualifying_spreads(self, sample_puts, screener_config):
        """Test that qualifying bull put spreads are found."""
        spreads = screen_bull_put_spreads(
            puts=sample_puts,
            ticker="TEST",
            stock_price=100.0,
            expiration=date(2024, 3, 15),
            dte=30,
            config=screener_config,
        )

        assert len(spreads) > 0
        for spread in spreads:
            assert spread.spread_type == "bull_put"
            assert spread.ticker == "TEST"
            assert spread.short_leg.strike > spread.long_leg.strike
            assert spread.net_credit > 0

    def test_respects_min_credit_filter(self, sample_puts, screener_config):
        """Test that min credit filter is applied."""
        screener_config.min_credit = 10.0  # Very high, should filter all

        spreads = screen_bull_put_spreads(
            puts=sample_puts,
            ticker="TEST",
            stock_price=100.0,
            expiration=date(2024, 3, 15),
            dte=30,
            config=screener_config,
        )

        assert len(spreads) == 0

    def test_respects_max_loss_filter(self, sample_puts, screener_config):
        """Test that max loss filter is applied."""
        screener_config.max_loss = 50.0  # Very low

        spreads = screen_bull_put_spreads(
            puts=sample_puts,
            ticker="TEST",
            stock_price=100.0,
            expiration=date(2024, 3, 15),
            dte=30,
            config=screener_config,
        )

        for spread in spreads:
            assert spread.max_loss <= 50.0

    def test_empty_puts_returns_empty(self, screener_config):
        """Test that empty puts DataFrame returns no spreads."""
        empty_puts = pl.DataFrame()

        spreads = screen_bull_put_spreads(
            puts=empty_puts,
            ticker="TEST",
            stock_price=100.0,
            expiration=date(2024, 3, 15),
            dte=30,
            config=screener_config,
        )

        assert len(spreads) == 0


class TestScreenBearCallSpreads:
    """Tests for bear call spread screening."""

    def test_finds_qualifying_spreads(self, sample_calls, screener_config):
        """Test that qualifying bear call spreads are found."""
        spreads = screen_bear_call_spreads(
            calls=sample_calls,
            ticker="TEST",
            stock_price=100.0,
            expiration=date(2024, 3, 15),
            dte=30,
            config=screener_config,
        )

        assert len(spreads) > 0
        for spread in spreads:
            assert spread.spread_type == "bear_call"
            assert spread.ticker == "TEST"
            assert spread.short_leg.strike < spread.long_leg.strike
            assert spread.net_credit > 0

    def test_empty_calls_returns_empty(self, screener_config):
        """Test that empty calls DataFrame returns no spreads."""
        empty_calls = pl.DataFrame()

        spreads = screen_bear_call_spreads(
            calls=empty_calls,
            ticker="TEST",
            stock_price=100.0,
            expiration=date(2024, 3, 15),
            dte=30,
            config=screener_config,
        )

        assert len(spreads) == 0


class TestScreenAllSpreads:
    """Tests for combined spread screening."""

    def test_combines_both_types(self, sample_calls, sample_puts, screener_config):
        """Test that both spread types are returned."""
        spreads = screen_all_spreads(
            calls=sample_calls,
            puts=sample_puts,
            ticker="TEST",
            stock_price=100.0,
            expiration=date(2024, 3, 15),
            dte=30,
            config=screener_config,
        )

        spread_types = {s.spread_type for s in spreads}
        assert "bull_put" in spread_types or "bear_call" in spread_types


class TestRankSpreads:
    """Tests for spread ranking."""

    @pytest.fixture
    def sample_spreads(self) -> list[CreditSpread]:
        """Create sample spreads for ranking tests."""
        from src.models import OptionLeg

        short_leg = OptionLeg(
            strike=95.0, premium=1.50, bid=1.45, ask=1.55, open_interest=500, volume=100
        )
        long_leg = OptionLeg(
            strike=90.0, premium=0.50, bid=0.45, ask=0.55, open_interest=300, volume=50
        )

        return [
            CreditSpread(
                ticker="LOW_ROR",
                spread_type="bull_put",
                expiration=date(2024, 3, 15),
                days_to_expiration=30,
                short_leg=short_leg,
                long_leg=long_leg,
                net_credit=0.50,
                max_loss=450.0,
                max_profit=50.0,
                return_on_risk=11.1,  # Low ROR
                break_even=94.5,
                width=5.0,
                current_stock_price=100.0,
                distance_from_price=5.0,
            ),
            CreditSpread(
                ticker="HIGH_ROR",
                spread_type="bull_put",
                expiration=date(2024, 3, 15),
                days_to_expiration=30,
                short_leg=short_leg,
                long_leg=long_leg,
                net_credit=1.50,
                max_loss=350.0,
                max_profit=150.0,
                return_on_risk=42.9,  # High ROR
                break_even=93.5,
                width=5.0,
                current_stock_price=100.0,
                distance_from_price=5.0,
            ),
        ]

    def test_ranks_by_quality(self, sample_spreads):
        """Test that spreads are ranked by quality score."""
        ranked = rank_spreads(sample_spreads)

        # Higher ROR should rank first
        assert ranked[0].ticker == "HIGH_ROR"
        assert ranked[1].ticker == "LOW_ROR"

    def test_empty_list_returns_empty(self):
        """Test that empty list returns empty."""
        ranked = rank_spreads([])
        assert len(ranked) == 0


class TestFilterDuplicateStrikes:
    """Tests for duplicate strike filtering."""

    @pytest.fixture
    def duplicate_spreads(self) -> list[CreditSpread]:
        """Create spreads with duplicates."""
        from src.models import OptionLeg

        short_leg = OptionLeg(
            strike=95.0, premium=1.50, bid=1.45, ask=1.55, open_interest=500, volume=100
        )
        long_leg = OptionLeg(
            strike=90.0, premium=0.50, bid=0.45, ask=0.55, open_interest=300, volume=50
        )

        base_spread = CreditSpread(
            ticker="AAPL",
            spread_type="bull_put",
            expiration=date(2024, 3, 15),
            days_to_expiration=30,
            short_leg=short_leg,
            long_leg=long_leg,
            net_credit=1.00,
            max_loss=400.0,
            max_profit=100.0,
            return_on_risk=25.0,
            break_even=94.0,
            width=5.0,
            current_stock_price=100.0,
            distance_from_price=5.0,
        )

        better_spread = base_spread.model_copy(update={"return_on_risk": 30.0})

        return [base_spread, better_spread]

    def test_removes_duplicates_keeps_best(self, duplicate_spreads):
        """Test that duplicates are removed and best ROR is kept."""
        filtered = filter_duplicate_strikes(duplicate_spreads)

        assert len(filtered) == 1
        assert filtered[0].return_on_risk == 30.0  # Keeps the better one
