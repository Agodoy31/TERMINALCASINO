from uuid import uuid4
from unittest.mock import patch
import pytest

from casino.accounts import Account
from casino.games.day_trading.models import Portfolio
from casino.games.day_trading.market import Market, Stock
from casino.games.day_trading.views import DAY_TRADING_HEADER, DayTradingView


def test_day_trading_header_constant():
    assert isinstance(DAY_TRADING_HEADER, str)
    assert len(DAY_TRADING_HEADER.strip()) > 0
    assert "DAY TRADING" in DAY_TRADING_HEADER.upper()


def test_get_total_pages_calculation():
    assert DayTradingView.get_total_pages(0, per_page=10) == 1
    assert DayTradingView.get_total_pages(10, per_page=10) == 1
    assert DayTradingView.get_total_pages(60, per_page=10) == 6
    assert DayTradingView.get_total_pages(65, per_page=10) == 7
    assert DayTradingView.get_total_pages(0) == 1
    assert DayTradingView.get_total_pages(25, per_page=5) == 5
    assert DayTradingView.get_total_pages(-5, per_page=10) == 1


def test_get_page_slice_boundaries_and_clamping():
    items = list(range(65))

    page_first = DayTradingView.get_page_slice(items, page=1, per_page=10)
    assert page_first == list(range(0, 10))
    assert len(page_first) == 10

    page_middle = DayTradingView.get_page_slice(items, page=4, per_page=10)
    assert page_middle == list(range(30, 40))
    assert len(page_middle) == 10

    page_last = DayTradingView.get_page_slice(items, page=7, per_page=10)
    assert page_last == list(range(60, 65))
    assert len(page_last) == 5

    page_clamp_lower = DayTradingView.get_page_slice(items, page=0, per_page=10)
    assert page_clamp_lower == list(range(0, 10))

    page_clamp_negative = DayTradingView.get_page_slice(items, page=-3, per_page=10)
    assert page_clamp_negative == list(range(0, 10))

    page_clamp_upper = DayTradingView.get_page_slice(items, page=8, per_page=10)
    assert page_clamp_upper == list(range(60, 65))

    page_clamp_huge = DayTradingView.get_page_slice(items, page=999, per_page=10)
    assert page_clamp_huge == list(range(60, 65))

    empty_slice = DayTradingView.get_page_slice([], page=1, per_page=10)
    assert empty_slice == []


def test_format_header_without_account():
    header = DayTradingView.format_header(None)
    assert "DAY TRADING" in header.upper()
    assert "Balance" not in header


def test_format_header_with_account():
    account = Account(uuid4(), "TraderBob", 1500)
    header = DayTradingView.format_header(account)
    assert "DAY TRADING" in header.upper()
    assert "TraderBob" in header
    assert "1500" in header


def test_format_news_banner_with_none_and_empty():
    assert DayTradingView.format_news_banner(None) == ""
    assert DayTradingView.format_news_banner("") == ""
    assert DayTradingView.format_news_banner("   ") == ""


def test_format_news_banner_with_news():
    headline = "Biotech firm secures regulatory approval for breakthrough therapy"
    banner = DayTradingView.format_news_banner(headline)
    assert headline in banner
    assert len(banner.splitlines()) >= 3


def test_format_market_table():
    stocks = [
        Stock(symbol="AAPL", name="Apple Inc.", price=185.50, previous_price=180.00, volatility=0.02),
        Stock(symbol="NVDA", name="NVIDIA Corp.", price=120.00, previous_price=125.00, volatility=0.04),
    ]
    table = DayTradingView.format_market_table(stocks, page=1, total_pages=4, tick_count=5)

    assert "SYMBOL" in table
    assert "NAME" in table
    assert "PRICE" in table
    assert "CHANGE" in table
    assert "% CHG" in table

    assert "AAPL" in table
    assert "Apple Inc." in table
    assert "185.50" in table
    assert "+5.50" in table
    assert "+3.06%" in table

    assert "NVDA" in table
    assert "NVIDIA Corp." in table
    assert "120.00" in table
    assert "-5.00" in table
    assert "-4.00%" in table

    assert "Page 1 of 4" in table
    assert "Market Tick 5" in table


def test_format_portfolio_summary_empty_holdings():
    portfolio = Portfolio(cash=1000.0, holdings={})
    summary = DayTradingView.format_portfolio_summary(portfolio, current_prices={})

    assert "Cash Balance" in summary
    assert "1000.00" in summary
    assert "Positions Value" in summary
    assert "0.00" in summary
    assert "Total Portfolio Value" in summary
    assert "No open stock positions" in summary


def test_format_portfolio_summary_populated_holdings():
    portfolio = Portfolio(cash=750.50, holdings={"AAPL": 10, "MSFT": 5})
    prices = {"AAPL": 150.00, "MSFT": 300.00}
    summary = DayTradingView.format_portfolio_summary(portfolio, current_prices=prices)

    assert "Cash Balance" in summary
    assert "750.50" in summary
    assert "Positions Value" in summary
    assert "3000.00" in summary
    assert "Total Portfolio Value" in summary
    assert "3750.50" in summary

    assert "AAPL" in summary
    assert "10" in summary
    assert "150.00" in summary
    assert "1500.00" in summary

    assert "MSFT" in summary
    assert "5" in summary
    assert "300.00" in summary
    assert "1500.00" in summary


def test_format_notice():
    assert DayTradingView.format_notice(None) == ""
    assert DayTradingView.format_notice("") == ""
    assert DayTradingView.format_notice("   ") == ""

    notice = DayTradingView.format_notice("Order filled: Bought 5 shares of AAPL")
    assert "Order filled: Bought 5 shares of AAPL" in notice


def test_format_menu():
    menu = DayTradingView.format_menu()
    expected_options = [
        "[B]uy",
        "[S]ell",
        "[N]ext Tick",
        "[P]age",
        "[D]eposit",
        "[W]ithdraw",
        "[E]xport",
        "[I]mport",
        "[Q]uit",
    ]
    for opt in expected_options:
        assert opt in menu


def test_render_screen_integrates_all_sections():
    market = Market(seed=42)
    market.last_news = "Semiconductor manufacturing subsidies approved by Senate"
    portfolio = Portfolio(cash=5000.0, holdings={"NVDA": 20})
    account = Account(uuid4(), "ActiveTrader", 2500)

    screen = DayTradingView.render_screen(
        portfolio=portfolio,
        market=market,
        page=1,
        notice="Transaction completed",
        account=account,
    )

    assert "DAY TRADING" in screen.upper()
    assert "ActiveTrader" in screen
    assert "Semiconductor manufacturing" in screen
    assert "SYMBOL" in screen
    assert "Page 1 of" in screen
    assert "Market Tick" in screen
    assert "Cash Balance" in screen
    assert "Transaction completed" in screen
    assert "[B]uy" in screen
    assert "[Q]uit" in screen


def test_display_screen_clears_and_prints(capsys):
    market = Market(seed=42)
    portfolio = Portfolio(cash=2000.0)

    with patch("casino.games.day_trading.views.clear_screen") as mock_clear:
        DayTradingView.display_screen(portfolio, market, page=1, notice=None)
        assert mock_clear.called

    captured = capsys.readouterr()
    assert "DAY TRADING" in captured.out.upper()
    assert "[B]uy" in captured.out


def test_prompt_and_announce(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda *args: "  b  ")
    result = DayTradingView.prompt("Choose option: ")
    assert result == "b"

    DayTradingView.announce("Market is closed")
    captured = capsys.readouterr()
    assert "Market is closed" in captured.out


def test_instance_and_class_usage():
    view = DayTradingView()
    assert view.ITEMS_PER_PAGE == 10
    assert view.get_total_pages(50, per_page=10) == 5
    slice_result = view.get_page_slice([1, 2, 3], page=1, per_page=2)
    assert slice_result == [1, 2]
