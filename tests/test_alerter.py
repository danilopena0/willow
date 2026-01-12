"""Tests for alerter module."""

import pytest
from datetime import date
from unittest.mock import patch, MagicMock

from src.models import OptionLeg, CreditSpread, AlertConfig
from src.alerter import (
    create_slack_blocks,
    send_slack_alert,
    send_alerts,
    AlertError,
)


@pytest.fixture
def sample_spreads() -> list[CreditSpread]:
    """Create sample spreads for alert tests."""
    short_leg = OptionLeg(
        strike=95.0, premium=1.50, bid=1.45, ask=1.55, open_interest=500, volume=100
    )
    long_leg = OptionLeg(
        strike=90.0, premium=0.50, bid=0.45, ask=0.55, open_interest=300, volume=50
    )

    return [
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
            days_to_expiration=35,
            short_leg=OptionLeg(
                strike=105.0, premium=1.30, bid=1.25, ask=1.35, open_interest=600, volume=200
            ),
            long_leg=OptionLeg(
                strike=110.0, premium=0.40, bid=0.35, ask=0.45, open_interest=400, volume=100
            ),
            net_credit=0.90,
            max_loss=410.0,
            max_profit=90.0,
            return_on_risk=36.0,  # High ROR for testing
            break_even=105.9,
            width=5.0,
            current_stock_price=100.0,
            distance_from_price=5.0,
        ),
    ]


@pytest.fixture
def slack_config() -> AlertConfig:
    """Create sample Slack alert config."""
    return AlertConfig(
        slack_webhook_url="https://hooks.slack.com/services/TEST/WEBHOOK",
    )


class TestCreateSlackBlocks:
    """Tests for Slack block creation."""

    def test_creates_valid_blocks(self, sample_spreads):
        """Test that valid Slack blocks are created."""
        blocks = create_slack_blocks(sample_spreads)

        assert isinstance(blocks, list)
        assert len(blocks) > 0

        # Check for header block
        headers = [b for b in blocks if b.get("type") == "header"]
        assert len(headers) > 0

    def test_includes_spread_count(self, sample_spreads):
        """Test that spread count is in header."""
        blocks = create_slack_blocks(sample_spreads)

        header = next(b for b in blocks if b.get("type") == "header")
        assert str(len(sample_spreads)) in header["text"]["text"]

    def test_limits_to_five_spreads(self, sample_spreads):
        """Test that only top 5 spreads are shown."""
        many_spreads = sample_spreads * 4  # 8 spreads
        blocks = create_slack_blocks(many_spreads)

        # Count section blocks with spread data
        spread_sections = [
            b for b in blocks
            if b.get("type") == "section" and "Strikes:" in str(b.get("text", {}))
        ]
        assert len(spread_sections) <= 5

    def test_includes_dashboard_path(self, sample_spreads):
        """Test that dashboard path is included when provided."""
        blocks = create_slack_blocks(sample_spreads, "/path/to/dashboard.html")

        # Should have context block with path
        context_blocks = [b for b in blocks if b.get("type") == "context"]
        assert len(context_blocks) > 0

    def test_includes_distance_percent(self, sample_spreads):
        """Test that distance percentage is included."""
        blocks = create_slack_blocks(sample_spreads)

        # Find spread sections and check for Dist:
        spread_sections = [
            b for b in blocks
            if b.get("type") == "section" and "Strikes:" in str(b.get("text", {}))
        ]
        assert any("Dist:" in str(s) for s in spread_sections)

    def test_color_coded_ror(self, sample_spreads):
        """Test that ROR is color coded with emojis."""
        blocks = create_slack_blocks(sample_spreads)

        block_text = str(blocks)
        # Should have color emojis based on ROR thresholds
        assert any(emoji in block_text for emoji in ["🟢", "🟡", "🔵"])


class TestSendSlackAlert:
    """Tests for Slack sending."""

    def test_raises_error_when_not_configured(self, sample_spreads):
        """Test that error is raised when Slack not configured."""
        empty_config = AlertConfig()

        with pytest.raises(AlertError) as excinfo:
            send_slack_alert(sample_spreads, empty_config)

        assert "not configured" in str(excinfo.value).lower()

    @patch("src.alerter.requests.post")
    def test_sends_slack_message(self, mock_post, sample_spreads, slack_config):
        """Test that Slack message is sent."""
        mock_post.return_value.raise_for_status = MagicMock()

        send_slack_alert(sample_spreads, slack_config)

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == slack_config.slack_webhook_url
        assert "blocks" in call_args[1]["json"]

    @patch("src.alerter.requests.post")
    def test_handles_request_error(self, mock_post, sample_spreads, slack_config):
        """Test that request errors are handled."""
        mock_post.side_effect = Exception("Network error")

        with pytest.raises(AlertError):
            send_slack_alert(sample_spreads, slack_config)


class TestSendAlerts:
    """Tests for combined alert sending."""

    @patch("src.alerter.load_alert_config")
    @patch("src.alerter.send_slack_alert")
    def test_sends_slack_alert(self, mock_slack, mock_config, sample_spreads):
        """Test that Slack alert is sent when enabled."""
        mock_config.return_value = AlertConfig(
            slack_webhook_url="https://hooks.slack.com/test",
        )

        results = send_alerts(sample_spreads, enable_slack=True)

        mock_slack.assert_called_once()
        assert results["slack"] is True

    @patch("src.alerter.load_alert_config")
    def test_handles_unconfigured_gracefully(self, mock_config, sample_spreads):
        """Test that unconfigured alerts don't raise errors."""
        mock_config.return_value = AlertConfig()  # Nothing configured

        results = send_alerts(sample_spreads, enable_slack=True)

        assert results["slack"] is False

    @patch("src.alerter.load_alert_config")
    @patch("src.alerter.send_slack_alert")
    def test_handles_failure_gracefully(self, mock_slack, mock_config, sample_spreads):
        """Test that failures are handled without raising."""
        mock_config.return_value = AlertConfig(
            slack_webhook_url="https://hooks.slack.com/test",
        )
        mock_slack.side_effect = AlertError("Slack failed")

        results = send_alerts(sample_spreads, enable_slack=True)

        assert results["slack"] is False

    @patch("src.alerter.load_alert_config")
    def test_respects_enable_flag(self, mock_config, sample_spreads):
        """Test that alerts are not sent when enable_slack=False."""
        mock_config.return_value = AlertConfig(
            slack_webhook_url="https://hooks.slack.com/test",
        )

        with patch("src.alerter.send_slack_alert") as mock_slack:
            results = send_alerts(sample_spreads, enable_slack=False)

            mock_slack.assert_not_called()
            assert results["slack"] is False
