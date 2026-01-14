"""Excel export functionality for credit spread results."""

from datetime import datetime
from pathlib import Path

import xlsxwriter

from src.models import CreditSpread
from src.constants import EXCEL_FORMAT


def export_to_excel(
    spreads: list[CreditSpread],
    output_dir: Path,
    timestamp: datetime | None = None,
) -> str:
    """
    Export credit spreads to Excel with conditional formatting.

    Args:
        spreads: List of credit spreads to export
        output_dir: Directory to save the Excel file
        timestamp: Timestamp for filename (defaults to now)

    Returns:
        Path to saved Excel file, or empty string if no spreads
    """
    if not spreads:
        return ""

    timestamp = timestamp or datetime.now()
    output_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = output_dir / f"{timestamp.strftime('%Y%m%d_%H%M%S')}_spreads.xlsx"

    workbook = xlsxwriter.Workbook(str(xlsx_path))
    worksheet = workbook.add_worksheet("Spreads")

    # Define formats
    formats = _create_formats(workbook)

    # Write headers
    headers = [
        "Ticker", "Type", "Expiration", "DTE", "Width", "Short Strike", "Long Strike",
        "Credit", "Max Loss", "Max Profit", "ROR %", "Ann %", "POP %", "Break-Even",
        "Stock Price", "Distance %", "Short OI", "Long OI"
    ]
    _write_headers(worksheet, headers, formats["header"])

    # Set column widths
    col_widths = [10, 12, 12, 6, 7, 13, 13, 10, 11, 11, 9, 9, 8, 12, 12, 12, 10, 10]
    for col, width in enumerate(col_widths):
        worksheet.set_column(col, col, width)

    # Write data rows
    _write_data_rows(worksheet, spreads, formats)

    # Apply conditional formatting
    _apply_conditional_formatting(worksheet, len(spreads))

    # Freeze header row and add auto-filter
    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, len(spreads), len(headers) - 1)

    workbook.close()
    return str(xlsx_path)


def _create_formats(workbook: xlsxwriter.Workbook) -> dict:
    """Create Excel cell formats."""
    return {
        "header": workbook.add_format({
            "bold": True,
            "bg_color": "#4472C4",
            "font_color": "white",
            "border": 1,
            "align": "center",
        }),
        "money": workbook.add_format({"num_format": "$#,##0.00", "border": 1}),
        "percent": workbook.add_format({"num_format": "0.0%", "border": 1}),
        "number": workbook.add_format({"num_format": "#,##0", "border": 1}),
        "text": workbook.add_format({"border": 1}),
        "date": workbook.add_format({"num_format": "yyyy-mm-dd", "border": 1}),
    }


def _write_headers(worksheet, headers: list[str], header_fmt) -> None:
    """Write header row."""
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_fmt)


def _write_data_rows(worksheet, spreads: list[CreditSpread], formats: dict) -> None:
    """Write spread data rows."""
    for row, spread in enumerate(spreads, start=1):
        worksheet.write(row, 0, spread.ticker, formats["text"])
        worksheet.write(row, 1, spread.spread_type.replace("_", " ").title(), formats["text"])
        worksheet.write(row, 2, spread.expiration, formats["date"])
        worksheet.write(row, 3, spread.days_to_expiration, formats["number"])
        worksheet.write(row, 4, spread.width, formats["number"])
        worksheet.write(row, 5, spread.short_leg.strike, formats["money"])
        worksheet.write(row, 6, spread.long_leg.strike, formats["money"])
        worksheet.write(row, 7, spread.net_credit, formats["money"])
        worksheet.write(row, 8, spread.max_loss, formats["money"])
        worksheet.write(row, 9, spread.max_profit, formats["money"])
        worksheet.write(row, 10, spread.return_on_risk / 100, formats["percent"])
        worksheet.write(row, 11, spread.annualized_return / 100, formats["percent"])
        worksheet.write(row, 12, spread.probability_of_profit / 100, formats["percent"])
        worksheet.write(row, 13, spread.break_even, formats["money"])
        worksheet.write(row, 14, spread.current_stock_price, formats["money"])
        worksheet.write(row, 15, spread.distance_from_price_pct / 100, formats["percent"])
        worksheet.write(row, 16, spread.short_leg.open_interest, formats["number"])
        worksheet.write(row, 17, spread.long_leg.open_interest, formats["number"])


def _apply_conditional_formatting(worksheet, row_count: int) -> None:
    """Apply conditional formatting color scales to key columns."""
    if row_count == 0:
        return

    # ROR % (column index 10) - Red to Green gradient
    worksheet.conditional_format(1, 10, row_count, 10, {
        "type": "3_color_scale",
        "min_type": "num", "mid_type": "num", "max_type": "num",
        "min_value": EXCEL_FORMAT.ROR_MIN,
        "mid_value": EXCEL_FORMAT.ROR_MID,
        "max_value": EXCEL_FORMAT.ROR_MAX,
        "min_color": "#F8696B",
        "mid_color": "#FFEB84",
        "max_color": "#63BE7B",
    })

    # Annualized % (column index 11) - Red to Green gradient
    worksheet.conditional_format(1, 11, row_count, 11, {
        "type": "3_color_scale",
        "min_type": "num", "mid_type": "num", "max_type": "num",
        "min_value": EXCEL_FORMAT.ANNUALIZED_MIN,
        "mid_value": EXCEL_FORMAT.ANNUALIZED_MID,
        "max_value": EXCEL_FORMAT.ANNUALIZED_MAX,
        "min_color": "#F8696B",
        "mid_color": "#FFEB84",
        "max_color": "#63BE7B",
    })

    # POP % (column index 12) - Red to Green gradient
    worksheet.conditional_format(1, 12, row_count, 12, {
        "type": "3_color_scale",
        "min_type": "num", "mid_type": "num", "max_type": "num",
        "min_value": EXCEL_FORMAT.POP_MIN,
        "mid_value": EXCEL_FORMAT.POP_MID,
        "max_value": EXCEL_FORMAT.POP_MAX,
        "min_color": "#F8696B",
        "mid_color": "#FFEB84",
        "max_color": "#63BE7B",
    })

    # DTE (column index 3) - Red to Green gradient
    worksheet.conditional_format(1, 3, row_count, 3, {
        "type": "3_color_scale",
        "min_type": "num", "mid_type": "num", "max_type": "num",
        "min_value": EXCEL_FORMAT.DTE_MIN,
        "mid_value": EXCEL_FORMAT.DTE_MID,
        "max_value": EXCEL_FORMAT.DTE_MAX,
        "min_color": "#F8696B",
        "mid_color": "#FFFFFF",
        "max_color": "#63BE7B",
    })

    # Distance % (column index 15) - Red to Blue gradient
    worksheet.conditional_format(1, 15, row_count, 15, {
        "type": "3_color_scale",
        "min_type": "num", "mid_type": "num", "max_type": "num",
        "min_value": EXCEL_FORMAT.DISTANCE_MIN,
        "mid_value": EXCEL_FORMAT.DISTANCE_MID,
        "max_value": EXCEL_FORMAT.DISTANCE_MAX,
        "min_color": "#F8696B",
        "mid_color": "#FFEB84",
        "max_color": "#5B9BD5",
    })
