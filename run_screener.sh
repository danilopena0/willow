#!/bin/bash
# Options Credit Spread Screener - Daily Run Script
#
# Usage:
#   ./run_screener.sh              # Run with defaults
#   ./run_screener.sh --visualize  # Generate charts
#   ./run_screener.sh --alert      # Send alerts
#
# Crontab example (run weekdays at 9:35 AM ET, after market open):
#   35 9 * * 1-5 /path/to/willow/run_screener.sh --alert --visualize

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create logs directory if it doesn't exist
mkdir -p logs

# Timestamp for log file
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="logs/screener_${TIMESTAMP}.log"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run the screener with all passed arguments
echo "Starting options screener at $(date)" | tee -a "$LOG_FILE"
echo "Arguments: $@" | tee -a "$LOG_FILE"
echo "---" | tee -a "$LOG_FILE"

python -m src.screener "$@" 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

echo "---" | tee -a "$LOG_FILE"
echo "Screener completed at $(date) with exit code $EXIT_CODE" | tee -a "$LOG_FILE"

# Clean up old log files (keep last 30 days)
find logs -name "screener_*.log" -mtime +30 -delete 2>/dev/null || true

exit $EXIT_CODE
