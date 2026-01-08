"""Tests for alerter module."""

import pytest
from datetime import date
from unittest.mock import patch, MagicMock

from src.models import OptionLeg, CreditSpread, AlertConfig
from src.alerter import (
    create_email_body,
    create_slack_blocks,
    send_email_alert,
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
def email_config() -> AlertConfig:
    """Create sample email alert config."""
    return AlertConfig(
        gmail_address="test@gmail.com",
        gmail_app_password="testpassword",
        alert_email="recipient@example.com",
    )


@pytest.fixture
def slack_config() -> AlertConfig:
    """Create sample Slack alert config."""
    return AlertConfig(
        slack_webhook_url="https://hooks.slack.com/services/TEST/WEBHOOK",
    )


class TestCreateEmailBody:
    """Tests for email body creation."""

    def test_creates_html_body(self, sample_spreads):
        """Test that HTML body is created."""
        body = create_email_body(sample_spreads)

        assert "<html>" in body
        assert "<table>" in body
        assert "Credit Spread Opportunities" in body

    def test_includes_spread_data(self, sample_spreads):
        """Test that spread data is included in body."""
        body = create_email_body(sample_spreads)

        assert "AAPL" in body
        assert "MSFT" in body
        assert "Bull Put" in body
        assert "Bear Call" in body

    def test_highlights_high_ror(self, sample_spreads):
        """Test that high ROR spreads are highlighted."""
        body = create_email_body(sample_spreads)

        # High ROR spread should have highlight class
        assert "high-ror" in body

    def test_limits_to_ten_spreads(self, sample_spreads):
        """Test that body limits to 10 spreads."""
        # Create more than 10 spreads
        many_spreads = sample_spreads * 6  # 12 spreads
        body = create_email_body(many_spreads)

        # Should only show 10
        assert body.count("<tr") <= 12  # 10 data rows + header + closing


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


class TestSendEmailAlert:
    """Tests for email sending."""

    def test_raises_error_when_not_configured(self, sample_spreads):
        """Test that error is raised when email not configured."""
        empty_config = AlertConfig()

        with pytest.raises(AlertError) as excinfo:
            send_email_alert(sample_spreads, empty_config)

        assert "not configured" in str(excinfo.value).lower()

    @patch("src.alerter.smtplib.SMTP_SSL")
    def test_sends_email_when_configured(self, mock_smtp, sample_spreads, email_config):
        """Test that email is sent when properly configured."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        send_email_alert(sample_spreads, email_config)

        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()

    @patch("src.alerter.smtplib.SMTP_SSL")
    def test_includes_subject(self, mock_smtp, sample_spreads, email_config):
        """Test that custom subject is used."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        send_email_alert(
            sample_spreads, email_config, subject="Custom Subject"
        )

        # Check that send_message was called with message containing subject
        call_args = mock_server.send_message.call_args
        msg = call_args[0][0]
        assert msg["Subject"] == "Custom Subject"


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
    @patch("src.alerter.send_email_alert")
    @patch("src.alerter.send_slack_alert")
    def test_sends_both_alerts(
        self, mock_slack, mock_email, mock_config, sample_spreads
    ):
        """Test that both alert types can be sent."""
        mock_config.return_value = AlertConfig(
            gmail_address="test@gmail.com",
            gmail_app_password="pass",
            alert_email="to@example.com",
            slack_webhook_url="https://hooks.slack.com/test",
        )

        results = send_alerts(
            sample_spreads, enable_email=True, enable_slack=True
        )

        mock_email.assert_called_once()
        mock_slack.assert_called_once()

    @patch("src.alerter.load_alert_config")
    def test_handles_unconfigured_gracefully(self, mock_config, sample_spreads):
        """Test that unconfigured alerts don't raise errors."""
        mock_config.return_value = AlertConfig()  # Nothing configured

        results = send_alerts(sample_spreads, enable_email=True, enable_slack=True)

        assert results["email"] is False
        assert results["slack"] is False

    @patch("src.alerter.load_alert_config")
    @patch("src.alerter.send_email_alert")
    def test_continues_on_failure(self, mock_email, mock_config, sample_spreads):
        """Test that one failure doesn't stop other alerts."""
        mock_config.return_value = AlertConfig(
            gmail_address="test@gmail.com",
            gmail_app_password="pass",
            alert_email="to@example.com",
            slack_webhook_url="https://hooks.slack.com/test",
        )
        mock_email.side_effect = AlertError("Email failed")

        with patch("src.alerter.send_slack_alert") as mock_slack:
            results = send_alerts(
                sample_spreads, enable_email=True, enable_slack=True
            )

            # Slack should still be attempted
            mock_slack.assert_called_once()
            assert results["email"] is False
