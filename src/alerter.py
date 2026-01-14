"""Alert system for credit spread notifications via Slack."""

from datetime import datetime

import requests
import yfinance as yf

from src.models import CreditSpread, AlertConfig
from src.config import load_alert_config
from src.constants import VIX


class AlertError(Exception):
    """Custom exception for alert failures."""

    pass


def get_market_context() -> dict:
    """
    Fetch current market context (VIX, SPY trend).

    Returns:
        Dictionary with market data
    """
    context = {
        "vix": None,
        "vix_status": None,
        "spy_price": None,
        "spy_change_pct": None,
        "spy_trend": None,
    }

    try:
        # Get VIX
        vix = yf.Ticker("^VIX")
        vix_info = vix.info
        vix_price = vix_info.get("regularMarketPrice") or vix_info.get("previousClose", 0)
        context["vix"] = vix_price

        if vix_price < VIX.LOW:
            context["vix_status"] = "Low 😌"
        elif vix_price < VIX.NORMAL:
            context["vix_status"] = "Normal"
        elif vix_price < VIX.ELEVATED:
            context["vix_status"] = "Elevated ⚠️"
        else:
            context["vix_status"] = "High 🔥"

        # Get SPY
        spy = yf.Ticker("SPY")
        spy_info = spy.info
        spy_price = spy_info.get("regularMarketPrice") or spy_info.get("previousClose", 0)
        prev_close = spy_info.get("previousClose", spy_price)

        context["spy_price"] = spy_price
        if prev_close > 0:
            change_pct = ((spy_price - prev_close) / prev_close) * 100
            context["spy_change_pct"] = change_pct

            if change_pct > 0.5:
                context["spy_trend"] = f"▲ +{change_pct:.2f}%"
            elif change_pct < -0.5:
                context["spy_trend"] = f"▼ {change_pct:.2f}%"
            else:
                context["spy_trend"] = f"◆ {change_pct:+.2f}%"

    except Exception:
        # Silently fail - market context is optional
        pass

    return context


def create_slack_blocks(
    spreads: list[CreditSpread],
    dashboard_path: str | None = None,
) -> list[dict]:
    """
    Create Slack Block Kit message structure with rich formatting.

    Args:
        spreads: List of credit spreads
        dashboard_path: Optional dashboard path to mention

    Returns:
        List of Slack blocks
    """
    # Calculate summary stats
    avg_ror = sum(s.return_on_risk for s in spreads) / len(spreads) if spreads else 0
    avg_pop = sum(s.probability_of_profit for s in spreads) / len(spreads) if spreads else 0
    avg_ann = sum(s.annualized_return for s in spreads) / len(spreads) if spreads else 0
    bull_puts = sum(1 for s in spreads if s.spread_type == "bull_put")
    bear_calls = len(spreads) - bull_puts

    # Get unique tickers
    tickers = set(s.ticker for s in spreads)

    # Get market context
    market = get_market_context()

    # Build header
    timestamp = datetime.now().strftime("%b %d, %I:%M %p")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📊 {len(spreads)} Credit Spreads Found",
                "emoji": True,
            },
        },
    ]

    # Market context section
    market_text_parts = [f"*{timestamp}*"]
    if market["spy_price"] and market["spy_trend"]:
        market_text_parts.append(f"SPY: ${market['spy_price']:.2f} {market['spy_trend']}")
    if market["vix"]:
        market_text_parts.append(f"VIX: {market['vix']:.1f} ({market['vix_status']})")

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": " | ".join(market_text_parts)}],
    })

    # Summary stats
    summary_text = (
        f"📈 *Avg ROR:* {avg_ror:.1f}%  |  "
        f"🎯 *Avg POP:* {avg_pop:.0f}%  |  "
        f"📅 *Avg Ann:* {avg_ann:.0f}%\n"
        f"🐂 Bull Puts: {bull_puts}  |  🐻 Bear Calls: {bear_calls}  |  "
        f"🏷️ Tickers: {len(tickers)}"
    )

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": summary_text},
    })

    # Split into bull puts and bear calls
    bull_puts_list = [s for s in spreads if s.spread_type == "bull_put"]
    bear_calls_list = [s for s in spreads if s.spread_type == "bear_call"]

    def add_spread_block(spread: CreditSpread, index: int) -> dict:
        """Create a block for a single spread."""
        if spread.return_on_risk >= 35:
            ror_emoji = "🟢"
        elif spread.return_on_risk >= 28:
            ror_emoji = "🟡"
        else:
            ror_emoji = "🔵"

        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{ror_emoji} *{index}. {spread.ticker}* "
                    f"`${spread.short_leg.strike:.0f}/${spread.long_leg.strike:.0f}` "
                    f"(${spread.width:.0f}w)\n"
                    f"Credit: `${spread.net_credit:.2f}` → "
                    f"ROR: *{spread.return_on_risk:.1f}%* | "
                    f"Ann: *{spread.annualized_return:.0f}%* | "
                    f"POP: *{spread.probability_of_profit:.0f}%*\n"
                    f"DTE: {spread.days_to_expiration} | "
                    f"Dist: {spread.distance_from_price_pct:.1f}% | "
                    f"Max Loss: ${spread.max_loss:.0f}"
                ),
            },
        }

    # Top Bull Puts section
    if bull_puts_list:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🐂 Top Bull Puts ({len(bull_puts_list)} total)*",
            },
        })
        for i, spread in enumerate(bull_puts_list[:3], 1):
            blocks.append(add_spread_block(spread, i))

    # Top Bear Calls section
    if bear_calls_list:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🐻 Top Bear Calls ({len(bear_calls_list)} total)*",
            },
        })
        for i, spread in enumerate(bear_calls_list[:3], 1):
            blocks.append(add_spread_block(spread, i))

    # Dashboard path
    if dashboard_path:
        blocks.extend([
            {"type": "divider"},
            {
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": f"📁 Results saved to: `{dashboard_path}`",
                }],
            },
        ])

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
