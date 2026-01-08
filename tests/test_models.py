"""Tests for Pydantic models."""

import pytest
from datetime import date, datetime

from src.models import (
    OptionLeg,
    CreditSpread,
    ScreenerConfig,
    AlertConfig,
    ScreenerResult,
)


class TestOptionLeg:
    """Tests for OptionLeg model."""

    def test_option_leg_creation(self):
        """Test basic option leg creation."""
        leg = OptionLeg(
            strike=100.0,
            premium=1.50,
            bid=1.45,
            ask=1.55,
            delta=0.30,
            implied_volatility=0.25,
            open_interest=500,
            volume=100,
        )

        assert leg.strike == 100.0
        assert leg.premium == 1.50
        assert leg.bid == 1.45
        assert leg.ask == 1.55
        assert leg.delta == 0.30
        assert leg.open_interest == 500

    def test_negative_delta_normalized(self):
        """Test that negative delta is normalized to absolute value."""
        leg = OptionLeg(
            strike=100.0,
            premium=1.50,
            bid=1.45,
            ask=1.55,
            delta=-0.30,  # Negative delta (put)
            open_interest=100,
            volume=50,
        )

        assert leg.delta == 0.30  # Should be positive

    def test_spread_percentage_calculation(self):
        """Test bid-ask spread percentage calculation."""
        leg = OptionLeg(
            strike=100.0,
            premium=2.00,
            bid=1.90,
            ask=2.10,
            open_interest=100,
            volume=50,
        )

        # Spread is 0.20, premium is 2.00, so spread % = (0.20/2.00) * 100 = 10%
        assert leg.spread_percentage == pytest.approx(10.0)

    def test_zero_premium_spread_percentage(self):
        """Test spread percentage when premium is zero."""
        leg = OptionLeg(
            strike=100.0,
            premium=0.0,
            bid=0.0,
            ask=0.05,
            open_interest=0,
            volume=0,
        )

        assert leg.spread_percentage == 0.0


class TestCreditSpread:
    """Tests for CreditSpread model."""

    @pytest.fixture
    def sample_spread(self) -> CreditSpread:
        """Create a sample credit spread for testing."""
        short_leg = OptionLeg(
            strike=95.0,
            premium=1.50,
            bid=1.45,
            ask=1.55,
            delta=0.30,
            open_interest=500,
            volume=100,
        )
        long_leg = OptionLeg(
            strike=90.0,
            premium=0.50,
            bid=0.45,
            ask=0.55,
            delta=0.15,
            open_interest=300,
            volume=50,
        )

        return CreditSpread(
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

    def test_credit_spread_creation(self, sample_spread):
        """Test basic credit spread creation."""
        assert sample_spread.ticker == "AAPL"
        assert sample_spread.spread_type == "bull_put"
        assert sample_spread.net_credit == 1.00
        assert sample_spread.max_loss == 400.0
        assert sample_spread.return_on_risk == 25.0

    def test_distance_from_price_pct(self, sample_spread):
        """Test distance from price percentage calculation."""
        # Distance is 5.0, price is 100.0, so pct = 5%
        assert sample_spread.distance_from_price_pct == pytest.approx(5.0)

    def test_risk_reward_ratio(self, sample_spread):
        """Test risk to reward ratio calculation."""
        # Max loss 400, max profit 100, ratio = 4.0
        assert sample_spread.risk_reward_ratio == pytest.approx(4.0)

    def test_to_summary(self, sample_spread):
        """Test human-readable summary generation."""
        summary = sample_spread.to_summary()
        assert "AAPL" in summary
        assert "Bull Put" in summary
        assert "$95/$90" in summary
        assert "1.00" in summary
        assert "25.0%" in summary


class TestScreenerConfig:
    """Tests for ScreenerConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ScreenerConfig()

        assert len(config.tickers) > 0
        assert config.min_dte == 30
        assert config.max_dte == 45
        assert config.min_credit == 0.30
        assert config.min_return_on_risk == 20.0
        assert config.spread_width == 5

    def test_custom_config(self):
        """Test custom configuration values."""
        config = ScreenerConfig(
            tickers=["SPY", "QQQ"],
            min_dte=45,
            max_dte=60,
            min_return_on_risk=30.0,
        )

        assert config.tickers == ["SPY", "QQQ"]
        assert config.min_dte == 45
        assert config.max_dte == 60
        assert config.min_return_on_risk == 30.0

    def test_tickers_uppercased(self):
        """Test that tickers are automatically uppercased."""
        config = ScreenerConfig(tickers=["aapl", "msft", "Googl"])
        assert config.tickers == ["AAPL", "MSFT", "GOOGL"]

    def test_invalid_delta_range(self):
        """Test that invalid delta range raises error."""
        with pytest.raises(ValueError):
            ScreenerConfig(target_delta_short=(0.5, 0.3))  # low > high

        with pytest.raises(ValueError):
            ScreenerConfig(target_delta_short=(0.0, 0.5))  # low = 0

        with pytest.raises(ValueError):
            ScreenerConfig(target_delta_short=(0.3, 1.0))  # high = 1


class TestAlertConfig:
    """Tests for AlertConfig model."""

    def test_email_not_configured(self):
        """Test email configured property when not set."""
        config = AlertConfig()
        assert not config.email_configured

    def test_email_configured(self):
        """Test email configured property when fully set."""
        config = AlertConfig(
            gmail_address="test@gmail.com",
            gmail_app_password="password123",
            alert_email="recipient@example.com",
        )
        assert config.email_configured

    def test_slack_not_configured(self):
        """Test Slack configured property when not set."""
        config = AlertConfig()
        assert not config.slack_configured

    def test_slack_configured(self):
        """Test Slack configured property when set."""
        config = AlertConfig(slack_webhook_url="https://hooks.slack.com/xxx")
        assert config.slack_configured


class TestScreenerResult:
    """Tests for ScreenerResult model."""

    @pytest.fixture
    def sample_spreads(self) -> list[CreditSpread]:
        """Create sample spreads for testing."""
        short_leg = OptionLeg(
            strike=95.0, premium=1.50, bid=1.45, ask=1.55, open_interest=500, volume=100
        )
        long_leg = OptionLeg(
            strike=90.0, premium=0.50, bid=0.45, ask=0.55, open_interest=300, volume=50
        )

        spreads = [
            CreditSpread(
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
            ),
            CreditSpread(
                ticker="MSFT",
                spread_type="bear_call",
                expiration=date(2024, 3, 15),
                days_to_expiration=30,
                short_leg=short_leg,
                long_leg=long_leg,
                net_credit=1.20,
                max_loss=380.0,
                max_profit=120.0,
                return_on_risk=31.6,
                break_even=96.2,
                width=5.0,
                current_stock_price=100.0,
                distance_from_price=5.0,
            ),
        ]
        return spreads

    def test_result_computed_fields(self, sample_spreads):
        """Test computed fields on ScreenerResult."""
        result = ScreenerResult(
            timestamp=datetime.now(),
            config=ScreenerConfig(),
            spreads=sample_spreads,
            tickers_screened=2,
        )

        assert result.total_spreads == 2
        assert result.bull_put_count == 1
        assert result.bear_call_count == 1
        assert result.avg_return_on_risk == pytest.approx(28.3, rel=0.1)

    def test_empty_result(self):
        """Test result with no spreads."""
        result = ScreenerResult(
            timestamp=datetime.now(),
            config=ScreenerConfig(),
            spreads=[],
            tickers_screened=5,
        )

        assert result.total_spreads == 0
        assert result.avg_return_on_risk == 0.0
        assert result.bull_put_count == 0
        assert result.bear_call_count == 0
