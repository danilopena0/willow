"""Tests for Altair visualizer module."""

import pytest
from datetime import date
from pathlib import Path
import tempfile

import altair as alt
import polars as pl

from src.models import OptionLeg, CreditSpread
from src.visualizer import (
    spreads_to_dataframe,
    create_spread_dashboard,
    create_individual_spread_chart,
    create_top_spreads_table,
    create_payoff_diagram,
    save_all_visualizations,
)


@pytest.fixture
def sample_spreads() -> list[CreditSpread]:
    """Create sample spreads for visualization tests."""
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
            return_on_risk=21.95,
            break_even=105.9,
            width=5.0,
            current_stock_price=100.0,
            distance_from_price=5.0,
        ),
        CreditSpread(
            ticker="GOOGL",
            spread_type="bull_put",
            expiration=date(2024, 3, 22),
            days_to_expiration=37,
            short_leg=short_leg,
            long_leg=long_leg,
            net_credit=1.20,
            max_loss=380.0,
            max_profit=120.0,
            return_on_risk=31.6,
            break_even=93.8,
            width=5.0,
            current_stock_price=100.0,
            distance_from_price=5.0,
        ),
    ]
    return spreads


@pytest.fixture
def sample_price_history() -> pl.DataFrame:
    """Create sample price history for visualization tests."""
    return pl.DataFrame({
        "date": pl.date_range(date(2024, 1, 1), date(2024, 2, 14), eager=True),
        "open": [100.0 + i * 0.5 for i in range(45)],
        "high": [101.0 + i * 0.5 for i in range(45)],
        "low": [99.0 + i * 0.5 for i in range(45)],
        "close": [100.5 + i * 0.5 for i in range(45)],
        "volume": [1000000 + i * 10000 for i in range(45)],
    })


class TestSpreadsToDataframe:
    """Tests for spreads_to_dataframe helper."""

    def test_converts_spreads_to_dataframe(self, sample_spreads):
        """Test that spreads are converted to DataFrame."""
        df = spreads_to_dataframe(sample_spreads)

        assert isinstance(df, pl.DataFrame)
        assert len(df) == 3
        assert "ticker" in df.columns
        assert "return_on_risk" in df.columns

    def test_empty_spreads_returns_empty_df(self):
        """Test that empty list returns empty DataFrame."""
        df = spreads_to_dataframe([])
        assert df.is_empty()


class TestCreateSpreadDashboard:
    """Tests for dashboard creation."""

    def test_creates_html_file(self, sample_spreads):
        """Test that dashboard creates an HTML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = create_spread_dashboard(sample_spreads, tmpdir)

            assert Path(path).exists()
            assert path.endswith(".html")

            # Check file contains expected Vega-Lite content
            with open(path) as f:
                content = f.read()
                assert "vega" in content.lower() or "altair" in content.lower()

    def test_handles_empty_spreads(self):
        """Test that empty spreads list creates dashboard with message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = create_spread_dashboard([], tmpdir)

            assert Path(path).exists()

            with open(path) as f:
                content = f.read()
                assert "No spreads found" in content

    def test_creates_output_directory(self, sample_spreads):
        """Test that output directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "new_dashboards"
            path = create_spread_dashboard(sample_spreads, str(new_dir))

            assert new_dir.exists()
            assert Path(path).exists()


class TestCreateIndividualSpreadChart:
    """Tests for individual spread chart creation."""

    def test_creates_altair_chart(self, sample_spreads):
        """Test that an Altair chart is created."""
        spread = sample_spreads[0]
        chart = create_individual_spread_chart(spread)

        assert isinstance(chart, (alt.Chart, alt.LayerChart, alt.VConcatChart, alt.HConcatChart))

    def test_with_price_history(self, sample_spreads, sample_price_history):
        """Test chart creation with price history."""
        spread = sample_spreads[0]
        chart = create_individual_spread_chart(spread, sample_price_history)

        assert isinstance(chart, (alt.Chart, alt.LayerChart, alt.VConcatChart, alt.HConcatChart))

    def test_without_price_history(self, sample_spreads):
        """Test chart creation without price history."""
        spread = sample_spreads[0]
        chart = create_individual_spread_chart(spread, None)

        assert isinstance(chart, (alt.Chart, alt.LayerChart, alt.VConcatChart, alt.HConcatChart))

    def test_can_save_to_html(self, sample_spreads):
        """Test that chart can be saved to HTML."""
        spread = sample_spreads[0]
        chart = create_individual_spread_chart(spread)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "spread_chart.html"
            chart.save(str(path))
            assert path.exists()


class TestCreateTopSpreadsTable:
    """Tests for top spreads table creation."""

    def test_creates_altair_chart(self, sample_spreads):
        """Test that an Altair chart is created."""
        chart = create_top_spreads_table(sample_spreads, top_n=10)

        assert isinstance(chart, (alt.Chart, alt.LayerChart, alt.VConcatChart, alt.HConcatChart))

    def test_respects_top_n(self, sample_spreads):
        """Test that top_n parameter limits results."""
        chart = create_top_spreads_table(sample_spreads, top_n=2)

        # Chart should be created successfully
        assert isinstance(chart, (alt.Chart, alt.LayerChart, alt.VConcatChart, alt.HConcatChart))

    def test_handles_empty_spreads(self):
        """Test handling of empty spreads list."""
        chart = create_top_spreads_table([], top_n=10)

        assert isinstance(chart, alt.Chart)

    def test_can_save_to_html(self, sample_spreads):
        """Test that table can be saved to HTML."""
        chart = create_top_spreads_table(sample_spreads)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "table.html"
            chart.save(str(path))
            assert path.exists()


class TestCreatePayoffDiagram:
    """Tests for payoff diagram creation."""

    def test_bull_put_payoff(self, sample_spreads):
        """Test payoff diagram for bull put spread."""
        spread = sample_spreads[0]  # bull_put
        chart = create_payoff_diagram(spread)

        assert isinstance(chart, (alt.Chart, alt.LayerChart))

    def test_bear_call_payoff(self, sample_spreads):
        """Test payoff diagram for bear call spread."""
        spread = sample_spreads[1]  # bear_call
        chart = create_payoff_diagram(spread)

        assert isinstance(chart, (alt.Chart, alt.LayerChart))

    def test_can_save_to_html(self, sample_spreads):
        """Test that payoff diagram can be saved to HTML."""
        spread = sample_spreads[0]
        chart = create_payoff_diagram(spread)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "payoff.html"
            chart.save(str(path))
            assert path.exists()


class TestSaveAllVisualizations:
    """Tests for saving all visualizations."""

    def test_saves_multiple_files(self, sample_spreads):
        """Test that multiple visualization files are saved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = save_all_visualizations(sample_spreads, tmpdir)

            assert "dashboard" in saved
            assert "table" in saved
            assert Path(saved["dashboard"]).exists()
            assert Path(saved["table"]).exists()

    def test_saves_payoff_diagrams(self, sample_spreads):
        """Test that payoff diagrams are saved for top spreads."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = save_all_visualizations(sample_spreads, tmpdir)

            payoff_keys = [k for k in saved if k.startswith("payoff_")]
            assert len(payoff_keys) > 0

    def test_handles_empty_spreads(self):
        """Test that empty spreads still creates dashboard."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = save_all_visualizations([], tmpdir)

            assert "dashboard" in saved
            assert Path(saved["dashboard"]).exists()
