"""Alert system for credit spread notifications via Slack."""

import requests

from src.models import CreditSpread, AlertConfig
from src.config import load_alert_config


class AlertError(Exception):
    """Custom exception for alert failures."""

    pass


def create_slack_blocks(
    spreads: list[CreditSpread],
    dashboard_path: str | None = None,
) -> list[dict]:
    """
    Create Slack Block Kit message structure.

    Args:
        spreads: List of credit spreads
        dashboard_path: Optional dashboard path to mention

    Returns:
        List of Slack blocks
    """
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📊 {len(spreads)} Credit Spreads Found",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Top {min(5, len(spreads))} opportunities by Return on Risk*",
            },
        },
        {"type": "divider"},
    ]

    for i, spread in enumerate(spreads[:5], 1):
        # Color indicator based on ROR
        ror_emoji = "🟢" if spread.return_on_risk >= 30 else "🟡" if spread.return_on_risk >= 25 else "🔵"

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{ror_emoji} *{i}. {spread.ticker}* - {spread.spread_type.replace('_', ' ').title()}\n"
                        f"Strikes: `${spread.short_leg.strike:.0f}/${spread.long_leg.strike:.0f}` | "
                        f"Credit: `${spread.net_credit:.2f}` | "
                        f"ROR: *{spread.return_on_risk:.1f}%* | "
                        f"DTE: {spread.days_to_expiration} | "
                        f"Dist: {spread.distance_from_price_pct:.1f}%"
                    ),
                },
            }
        )

    if dashboard_path:
        blocks.extend(
            [
                {"type": "divider"},
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"📁 Dashboard saved to: `{dashboard_path}`",
                        }
                    ],
                },
            ]
        )

    return blocks


def send_slack_alert(
    spreads: list[CreditSpread],
    alert_config: AlertConfig | None = None,
    dashboard_path: str | None = None,
) -> None:
    """
    Send alert to Slack via webhook.

    Args:
        spreads: List of credit spreads to alert about
        alert_config: Alert configuration (uses env vars if not provided)
        dashboard_path: Optional path to dashboard to mention

    Raises:
        AlertError: If Slack message fails to send
    """
    if alert_config is None:
        alert_config = load_alert_config()

    if not alert_config.slack_configured:
        raise AlertError("Slack not configured. Set SLACK_WEBHOOK_URL.")

    blocks = create_slack_blocks(spreads, dashboard_path)

    try:
        response = requests.post(
            alert_config.slack_webhook_url,
            json={"blocks": blocks},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise AlertError(f"Failed to send Slack message: {e}")


def send_alerts(
    spreads: list[CreditSpread],
    enable_slack: bool = False,
    dashboard_path: str | None = None,
) -> dict[str, bool]:
    """
    Send alerts through Slack.

    Args:
        spreads: List of credit spreads to alert about
        enable_slack: Whether to send Slack alerts
        dashboard_path: Optional dashboard path

    Returns:
        Dictionary with status of alert
    """
    results = {"slack": False}
    alert_config = load_alert_config()

    if enable_slack and alert_config.slack_configured:
        try:
            send_slack_alert(spreads, alert_config, dashboard_path)
            results["slack"] = True
        except AlertError as e:
            print(f"Slack alert failed: {e}")

    return results


def test_slack_connection() -> bool:
    """
    Test Slack webhook configuration.

    Returns:
        True if test message sent successfully
    """
    alert_config = load_alert_config()

    if not alert_config.slack_configured:
        print("Slack not configured. Set SLACK_WEBHOOK_URL in .env")
        return False

    try:
        response = requests.post(
            alert_config.slack_webhook_url,
            json={"text": "✅ Test message from Willow Options Screener"},
            timeout=10,
        )
        response.raise_for_status()
        print("Slack connection successful")
        return True
    except Exception as e:
        print(f"Slack connection failed: {e}")
        return False
