# Willow - Options Credit Spread Screener

A Python command-line tool for screening options credit spread opportunities across a watchlist of securities. Features interactive Altair visualizations, configurable Slack alerts, and historical tracking.

## Features

- Screen for **bull put spreads** (bullish) and **bear call spreads** (bearish)
- **Probability of Profit (POP)** calculation using Black-Scholes delta
- **Annualized return** calculation for comparing across different DTEs
- **Multi-width scanning** ($1, $2, $5, etc. spreads in one run)
- **Earnings filter** to skip tickers with upcoming earnings
- Fetch real-time options chains via **yfinance**
- **Parallel fetching** with ThreadPoolExecutor for faster screening
- **API response caching** (5-minute expiry) to reduce redundant calls
- Fast data processing with **Polars**
- Type-safe models with **Pydantic**
- Interactive dashboards with **Altair**
- Configurable filtering (delta, DTE, ROR, distance, liquidity)
- **Slack alerts** with market context (VIX, SPY trend) and separate bull/bear sections
- Excel output with conditional formatting
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

# Scan multiple spread widths
python -m src.screener --widths 1 2 5 10

# Skip tickers with earnings in the next 7 days
python -m src.screener --earnings-buffer 7
```

### Generate Visualizations

```bash
# Create interactive dashboard
python -m src.screener --visualize

# Dashboard saved to data/dashboards/dashboard_YYYYMMDD_HHMMSS.html
```

### Send Slack Alerts

```bash
# Test alert configuration
python -m src.screener --test-alerts

# Send alerts for high-quality spreads
python -m src.screener --alert --slack
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
| `--max-ror` | Maximum return on risk (%) - filters unrealistic | 75 |
| `--min-distance` | Minimum distance from price (%) | 5 |
| `--min-dte` | Minimum days to expiration | 30 |
| `--max-dte` | Maximum days to expiration | 45 |
| `--min-credit` | Minimum net credit ($) | 0.20 |
| `--max-loss` | Maximum loss per spread ($) | 500 |
| `--widths` | Space-separated spread widths ($) | 1 2 5 |
| `--earnings-buffer` | Skip tickers with earnings within N days (0=off) | 0 |
| `--min-oi` | Minimum open interest | 50 |
| `--visualize`, `-v` | Generate Altair charts | false |
| `--alert`, `-a` | Send alerts | false |
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
SCREENER_MAX_ROR=75
SCREENER_MIN_DISTANCE=5
SCREENER_SPREAD_WIDTHS=1,2,5
SCREENER_EARNINGS_BUFFER=0

# Slack alerts
ENABLE_SLACK_ALERTS=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### Slack Setup

1. Go to [Slack Apps](https://api.slack.com/apps)
2. Create a new app (From scratch)
3. Add "Incoming Webhooks" feature
4. Activate webhooks and create one for your channel
5. Copy the webhook URL to `SLACK_WEBHOOK_URL` in your `.env`

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
│   └── alerter.py           # Slack notifications
├── tests/
│   ├── test_models.py
│   ├── test_calculator.py
│   ├── test_visualizer.py
│   └── test_alerter.py
├── data/
│   ├── results/             # Daily Excel files
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
- **Annualized Return**: ROR × (365 / DTE) - useful for comparing different expirations
- **Probability of Profit (POP)**: 1 - |delta| (e.g., 0.30 delta = 70% POP)
- **Days to Expiration (DTE)**: Time until option expires
- **Delta**: Calculated using Black-Scholes model from implied volatility
- **Distance %**: How far the short strike is from current price (safety buffer)
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
6. Arguments: `-m src.screener --visualize --alert --slack`
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
