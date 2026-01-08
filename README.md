# Willow - Options Credit Spread Screener

A Python command-line tool for screening options credit spread opportunities across a watchlist of securities. Features interactive Altair visualizations, configurable alerts via email/Slack, and historical tracking.

## Features

- Screen for **bull put spreads** (bullish) and **bear call spreads** (bearish)
- Fetch real-time options chains via **yfinance**
- Fast data processing with **Polars**
- Type-safe models with **Pydantic**
- Interactive dashboards with **Altair**
- Configurable filtering (delta, DTE, return on risk, liquidity)
- Alert system (Gmail SMTP, Slack webhooks)
- Historical tracking in Parquet format
- Automated daily execution via cron

## Installation

### Prerequisites

- Python 3.11+
- pip or uv package manager

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/willow.git
cd willow

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit .env with your settings (optional)
```

## Usage

### Basic Screening

```bash
# Run with default configuration
python -m src.screener

# Screen specific tickers
python -m src.screener --tickers AAPL MSFT GOOGL NVDA

# Custom filters
python -m src.screener --min-ror 25 --max-dte 60 --min-credit 0.50
```

### Generate Visualizations

```bash
# Create interactive dashboard
python -m src.screener --visualize

# Dashboard saved to data/dashboards/dashboard_YYYYMMDD_HHMMSS.html
```

### Send Alerts

```bash
# Test alert configuration
python -m src.screener --test-alerts

# Send alerts for high-quality spreads
python -m src.screener --alert --slack
python -m src.screener --alert --email
```

### Full Daily Run

```bash
# Complete screening with visualizations and alerts
python -m src.screener --visualize --alert --slack

# Or use the bash script
./run_screener.sh --visualize --alert
```

## CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--tickers` | Space-separated list of tickers | Config default |
| `--min-ror` | Minimum return on risk (%) | 20 |
| `--min-dte` | Minimum days to expiration | 30 |
| `--max-dte` | Maximum days to expiration | 45 |
| `--min-credit` | Minimum net credit ($) | 0.30 |
| `--max-loss` | Maximum loss per spread ($) | 500 |
| `--spread-width` | Strike width ($) | 5 |
| `--min-oi` | Minimum open interest | 50 |
| `--visualize`, `-v` | Generate Altair charts | false |
| `--alert`, `-a` | Send alerts | false |
| `--email` | Enable email alerts | false |
| `--slack` | Enable Slack alerts | false |
| `--quiet`, `-q` | Suppress output | false |
| `--test-alerts` | Test alert config | - |

## Configuration

### Environment Variables

Create a `.env` file (see `.env.example`):

```bash
# Screener settings
SCREENER_TICKERS=SPY,QQQ,AAPL,MSFT,GOOGL
SCREENER_MIN_DTE=30
SCREENER_MAX_DTE=45
SCREENER_MIN_ROR=20

# Email alerts (Gmail)
ENABLE_EMAIL_ALERTS=true
GMAIL_ADDRESS=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-password
ALERT_EMAIL=recipient@example.com

# Slack alerts
ENABLE_SLACK_ALERTS=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### Gmail Setup

1. Enable 2-Factor Authentication on your Google account
2. Go to [App Passwords](https://myaccount.google.com/apppasswords)
3. Generate a new app password for "Mail"
4. Use this password in `GMAIL_APP_PASSWORD`

### Slack Setup

1. Create a [Slack App](https://api.slack.com/apps)
2. Add "Incoming Webhooks" feature
3. Create a webhook for your channel
4. Copy the webhook URL to `SLACK_WEBHOOK_URL`

## Project Structure

```
willow/
├── src/
│   ├── __init__.py
│   ├── screener.py          # Main CLI script
│   ├── models.py            # Pydantic data models
│   ├── config.py            # Configuration management
│   ├── options_fetcher.py   # yfinance wrapper
│   ├── spread_calculator.py # Spread screening logic
│   ├── visualizer.py        # Altair charts
│   └── alerter.py           # Email/Slack notifications
├── tests/
│   ├── test_models.py
│   ├── test_calculator.py
│   ├── test_visualizer.py
│   └── test_alerter.py
├── data/
│   ├── results/             # Daily Parquet files
│   ├── dashboards/          # HTML visualizations
│   └── history/             # Historical tracking
├── logs/                    # Execution logs
├── .env.example
├── .gitignore
├── requirements.txt
├── run_screener.sh
└── README.md
```

## Credit Spread Basics

### Bull Put Spread (Bullish Strategy)

- **Sell** a put at a higher strike (receive premium)
- **Buy** a put at a lower strike (pay premium)
- **Profit** when stock stays above short strike at expiration
- **Max profit** = Net credit received
- **Max loss** = Spread width - Net credit

### Bear Call Spread (Bearish Strategy)

- **Sell** a call at a lower strike (receive premium)
- **Buy** a call at a higher strike (pay premium)
- **Profit** when stock stays below short strike at expiration
- **Max profit** = Net credit received
- **Max loss** = Spread width - Net credit

### Key Metrics

- **Return on Risk (ROR)**: Net credit / Max loss (as percentage)
- **Days to Expiration (DTE)**: Time until option expires
- **Delta**: Probability proxy (0.30 delta ≈ 30% ITM probability)
- **Break-even**: Price where P&L = 0 at expiration

## Automation

### Cron Setup (Linux/Mac)

```bash
# Edit crontab
crontab -e

# Run weekdays at 9:35 AM ET (after market open)
35 9 * * 1-5 /path/to/willow/run_screener.sh --visualize --alert >> /path/to/willow/logs/cron.log 2>&1
```

### Task Scheduler (Windows)

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily, weekdays, 9:35 AM
4. Action: Start a program
5. Program: `python`
6. Arguments: `-m src.screener --visualize --alert`
7. Start in: `C:\path\to\willow`

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_calculator.py -v
```

## Phase 2 Roadmap

Future enhancements (uncomment in requirements.txt):

- **TA-Lib**: Technical indicators (RSI, support/resistance)
- **Instructor/Claude**: AI analysis and recommendations
- **Prophet**: Price forecasting for probability calculations
- **DuckDB**: Fast SQL analytics on historical data
- **Backtesting**: Analyze which criteria yield best results

## License

MIT License - see LICENSE file for details.

## Disclaimer

This tool is for educational and informational purposes only. Options trading involves significant risk of loss. Past performance does not guarantee future results. Always do your own research and consider consulting a financial advisor before trading.
