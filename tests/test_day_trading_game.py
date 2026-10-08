from uuid import uuid4
from unittest.mock import MagicMock, patch
import json
import pytest

from casino.accounts import Account
from casino.config import Config
from casino.types import GameContext
from casino.games.day_trading.models import Portfolio, TradeRecord
from casino.games.day_trading.market import Market, Stock
from casino.games.day_trading.views import DayTradingView
from casino.games.day_trading.game import DayTradingGame, play_day_trading


class MockTradingView:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.displayed_screens = []

    def prompt(self, prompt_text=""):
        if self.responses:
            return self.responses.pop(0)
        return ""

    def display_screen(self, portfolio, market, page, notice, account):
        self.displayed_screens.append({
            "portfolio": portfolio,
            "market": market,
            "page": page,
            "notice": notice,
            "account": account,
        })


@pytest.fixture
def test_context():
    account = Account(aid=uuid4(), name="Alice", balance=500)
    config = Config.default()
    return GameContext(account=account, config=config)


def test_game_initialization_defaults(test_context):
    game = DayTradingGame(context=test_context)
    assert game.context is test_context
    assert game.account is test_context.account
    assert isinstance(game.market, Market)
    assert isinstance(game.portfolio, Portfolio)
    assert isinstance(game.view, DayTradingView)
    assert game.current_page == 1
    assert game.notice == ""
    assert game.running is True
    assert game.save_path == "portfolio.json"


def test_game_initialization_custom(test_context):
    custom_portfolio = Portfolio(cash=250.0)
    custom_market = Market(seed=42)
    custom_view = MockTradingView()
    custom_path = "custom_save.json"

    game = DayTradingGame(
        context=test_context,
        portfolio=custom_portfolio,
        market=custom_market,
        view=custom_view,
        save_path=custom_path,
    )
    assert game.portfolio is custom_portfolio
    assert game.market is custom_market
    assert game.view is custom_view
    assert game.save_path == custom_path


def test_handle_command_case_insensitivity(test_context):
    game = DayTradingGame(context=test_context)
    with patch.object(game, "handle_buy") as mock_buy:
        game.handle_command("b")
        assert mock_buy.call_count == 1
        game.handle_command("B")
        assert mock_buy.call_count == 2


def test_handle_command_dispatch_all(test_context):
    game = DayTradingGame(context=test_context)
    commands = {
        "b": "handle_buy",
        "s": "handle_sell",
        "n": "handle_next_tick",
        "p": "handle_page",
        "d": "handle_deposit",
        "w": "handle_withdraw",
        "e": "handle_export",
        "i": "handle_import",
        "q": "handle_quit",
    }
    for cmd, handler_name in commands.items():
        with patch.object(game, handler_name) as mock_handler:
            game.handle_command(cmd)
            assert mock_handler.call_count == 1
            game.handle_command(cmd.upper())
            assert mock_handler.call_count == 2


def test_handle_command_invalid(test_context):
    game = DayTradingGame(context=test_context)
    game.handle_command("xyz")
    assert "xyz" in game.notice
    assert game.running is True

    game.handle_command("")
    assert len(game.notice) > 0


def test_handle_buy_valid(test_context):
    view = MockTradingView(["AAPL", "2"])
    game = DayTradingGame(context=test_context, view=view)
    price = game.market.get_price("AAPL")
    initial_cash = game.portfolio.cash
    expected_cost = round(2 * price, 2)

    game.handle_buy()

    assert game.portfolio.holdings.get("AAPL") == 2
    assert game.portfolio.cash == round(initial_cash - expected_cost, 2)
    assert "AAPL" in game.notice
    assert "Bought 2 shares" in game.notice


def test_handle_buy_empty_ticker(test_context):
    view = MockTradingView([""])
    game = DayTradingGame(context=test_context, view=view)
    initial_cash = game.portfolio.cash

    game.handle_buy()

    assert game.portfolio.cash == initial_cash
    assert game.portfolio.holdings == {}


def test_handle_buy_unknown_ticker(test_context):
    view = MockTradingView(["NONEXISTENT"])
    game = DayTradingGame(context=test_context, view=view)
    initial_cash = game.portfolio.cash

    game.handle_buy()

    assert game.portfolio.cash == initial_cash
    assert "Unknown ticker" in game.notice


def test_handle_buy_non_numeric_shares(test_context):
    view = MockTradingView(["AAPL", "five"])
    game = DayTradingGame(context=test_context, view=view)
    initial_cash = game.portfolio.cash

    game.handle_buy()

    assert game.portfolio.cash == initial_cash
    assert "Invalid shares count" in game.notice


def test_handle_buy_non_positive_shares(test_context):
    view = MockTradingView(["AAPL", "0"])
    game = DayTradingGame(context=test_context, view=view)
    initial_cash = game.portfolio.cash

    game.handle_buy()

    assert game.portfolio.cash == initial_cash
    assert "positive integer" in game.notice

    view.responses = ["AAPL", "-3"]
    game.handle_buy()
    assert "positive integer" in game.notice


def test_handle_buy_insufficient_funds(test_context):
    view = MockTradingView(["AAPL", "999999"])
    game = DayTradingGame(context=test_context, view=view)
    initial_cash = game.portfolio.cash

    game.handle_buy()

    assert game.portfolio.cash == initial_cash
    assert "AAPL" not in game.portfolio.holdings
    assert "Insufficient funds" in game.notice


def test_handle_sell_valid(test_context):
    portfolio = Portfolio(cash=100.0, holdings={"AAPL": 5})
    view = MockTradingView(["AAPL", "2"])
    game = DayTradingGame(context=test_context, portfolio=portfolio, view=view)
    price = game.market.get_price("AAPL")
    expected_proceeds = round(2 * price, 2)

    game.handle_sell()

    assert game.portfolio.holdings.get("AAPL") == 3
    assert game.portfolio.cash == round(100.0 + expected_proceeds, 2)
    assert "Sold 2 shares" in game.notice


def test_handle_sell_full_liquidation(test_context):
    portfolio = Portfolio(cash=50.0, holdings={"AAPL": 4})
    view = MockTradingView(["AAPL", "4"])
    game = DayTradingGame(context=test_context, portfolio=portfolio, view=view)

    game.handle_sell()

    assert "AAPL" not in game.portfolio.holdings
    assert "Sold 4 shares" in game.notice


def test_handle_sell_empty_ticker(test_context):
    view = MockTradingView([""])
    game = DayTradingGame(context=test_context, view=view)

    game.handle_sell()

    assert game.notice == ""


def test_handle_sell_unowned_ticker(test_context):
    view = MockTradingView(["MSFT"])
    game = DayTradingGame(context=test_context, view=view)

    game.handle_sell()

    assert "No shares of MSFT owned" in game.notice


def test_handle_sell_non_numeric_shares(test_context):
    portfolio = Portfolio(cash=100.0, holdings={"AAPL": 5})
    view = MockTradingView(["AAPL", "many"])
    game = DayTradingGame(context=test_context, portfolio=portfolio, view=view)

    game.handle_sell()

    assert game.portfolio.holdings["AAPL"] == 5
    assert "Invalid shares count" in game.notice


def test_handle_sell_non_positive_shares(test_context):
    portfolio = Portfolio(cash=100.0, holdings={"AAPL": 5})
    view = MockTradingView(["AAPL", "0"])
    game = DayTradingGame(context=test_context, portfolio=portfolio, view=view)

    game.handle_sell()

    assert game.portfolio.holdings["AAPL"] == 5
    assert "positive integer" in game.notice

    view.responses = ["AAPL", "-2"]
    game.handle_sell()
    assert "positive integer" in game.notice


def test_handle_sell_excess_shares(test_context):
    portfolio = Portfolio(cash=100.0, holdings={"AAPL": 2})
    view = MockTradingView(["AAPL", "10"])
    game = DayTradingGame(context=test_context, portfolio=portfolio, view=view)

    game.handle_sell()

    assert game.portfolio.holdings["AAPL"] == 2
    assert "only 2 shares owned" in game.notice


def test_handle_sell_market_price_unavailable(test_context):
    portfolio = Portfolio(cash=100.0, holdings={"DELISTED": 5})
    view = MockTradingView(["DELISTED", "2"])
    game = DayTradingGame(context=test_context, portfolio=portfolio, view=view)

    game.handle_sell()

    assert "Unable to fetch market price" in game.notice


def test_handle_next_tick_advances(test_context):
    game = DayTradingGame(context=test_context)
    initial_tick = game.market.tick_count

    game.handle_next_tick()

    assert game.market.tick_count == initial_tick + 1
    assert f"Advanced to tick {initial_tick + 1}" in game.notice


def test_handle_next_tick_with_news(test_context):
    game = DayTradingGame(context=test_context)
    with patch.object(game.market, "advance_tick") as mock_advance:
        game.market.tick_count = 5
        game.market.last_news = "Breaking News Tech Rally"
        game.handle_next_tick()
        assert mock_advance.call_count == 1
        assert "Advanced to tick 5" in game.notice
        assert "Breaking News Tech Rally" in game.notice


def test_handle_page_advancement_and_wrap(test_context):
    game = DayTradingGame(context=test_context)
    total_pages = DayTradingView.get_total_pages(len(game.market.get_quotes()), DayTradingView.ITEMS_PER_PAGE)
    assert total_pages >= 2

    assert game.current_page == 1
    game.handle_page()
    assert game.current_page == 2
    assert f"Page 2 of {total_pages}" in game.notice

    game.current_page = total_pages
    game.handle_page()
    assert game.current_page == 1
    assert f"Page 1 of {total_pages}" in game.notice


def test_handle_deposit_valid(test_context):
    view = MockTradingView(["100"])
    game = DayTradingGame(context=test_context, view=view)
    initial_balance = test_context.account.balance
    initial_cash = game.portfolio.cash

    game.handle_deposit()

    assert test_context.account.balance == initial_balance - 100
    assert game.portfolio.cash == initial_cash + 100
    assert "Deposited 100 chips" in game.notice


def test_handle_deposit_non_numeric(test_context):
    view = MockTradingView(["abc"])
    game = DayTradingGame(context=test_context, view=view)

    game.handle_deposit()

    assert "Invalid deposit amount" in game.notice


def test_handle_deposit_non_positive(test_context):
    view = MockTradingView(["0"])
    game = DayTradingGame(context=test_context, view=view)

    game.handle_deposit()

    assert "positive integer" in game.notice

    view.responses = ["-50"]
    game.handle_deposit()
    assert "positive integer" in game.notice


def test_handle_deposit_insufficient_balance(test_context):
    view = MockTradingView(["999999"])
    game = DayTradingGame(context=test_context, view=view)

    game.handle_deposit()

    assert "Insufficient account balance" in game.notice


def test_handle_deposit_value_error_caught(test_context):
    view = MockTradingView(["50"])
    game = DayTradingGame(context=test_context, view=view)
    with patch.object(game.portfolio, "deposit_from_account", side_effect=ValueError("Account locked")):
        game.handle_deposit()
        assert "Deposit failed" in game.notice
        assert "Account locked" in game.notice


def test_handle_withdraw_valid(test_context):
    view = MockTradingView(["75"])
    game = DayTradingGame(context=test_context, view=view)
    initial_balance = test_context.account.balance
    initial_cash = game.portfolio.cash

    game.handle_withdraw()

    assert test_context.account.balance == initial_balance + 75
    assert game.portfolio.cash == initial_cash - 75
    assert "Withdrew 75 chips" in game.notice


def test_handle_withdraw_non_numeric(test_context):
    view = MockTradingView(["lots"])
    game = DayTradingGame(context=test_context, view=view)

    game.handle_withdraw()

    assert "Invalid withdrawal amount" in game.notice


def test_handle_withdraw_non_positive(test_context):
    view = MockTradingView(["-10"])
    game = DayTradingGame(context=test_context, view=view)

    game.handle_withdraw()

    assert "positive integer" in game.notice


def test_handle_withdraw_insufficient_portfolio_cash(test_context):
    view = MockTradingView(["50000"])
    game = DayTradingGame(context=test_context, view=view)

    game.handle_withdraw()

    assert "Insufficient portfolio cash" in game.notice


def test_handle_withdraw_value_error_caught(test_context):
    view = MockTradingView(["50"])
    game = DayTradingGame(context=test_context, view=view)
    with patch.object(game.portfolio, "withdraw_to_account", side_effect=ValueError("Transfer error")):
        game.handle_withdraw()
        assert "Withdrawal failed" in game.notice
        assert "Transfer error" in game.notice


def test_handle_export_and_import_cycle(test_context, tmp_path):
    export_file = str(tmp_path / "saved_portfolio.json")
    view_export = MockTradingView([export_file])
    portfolio_export = Portfolio(cash=450.0, holdings={"NVDA": 8})
    game_export = DayTradingGame(
        context=test_context,
        portfolio=portfolio_export,
        view=view_export,
    )

    game_export.handle_export()

    assert f"Exported portfolio to {export_file}" in game_export.notice

    view_import = MockTradingView([export_file])
    game_import = DayTradingGame(context=test_context, view=view_import)

    game_import.handle_import()

    assert f"Imported portfolio from {export_file}" in game_import.notice
    assert game_import.portfolio.cash == 450.0
    assert game_import.portfolio.holdings.get("NVDA") == 8


def test_handle_export_default_path(test_context, tmp_path):
    default_file = str(tmp_path / "default_save.json")
    view = MockTradingView([""])
    game = DayTradingGame(context=test_context, view=view, save_path=default_file)

    game.handle_export()

    assert f"Exported portfolio to {default_file}" in game.notice


def test_handle_export_error_caught(test_context):
    view = MockTradingView(["invalid/nonexistent/dir/file.json"])
    game = DayTradingGame(context=test_context, view=view)
    with patch.object(game.portfolio, "save_json", side_effect=IOError("Permission denied")):
        game.handle_export()
        assert "Export failed" in game.notice


def test_handle_import_error_caught(test_context, tmp_path):
    bad_file = str(tmp_path / "does_not_exist.json")
    view = MockTradingView([bad_file])
    game = DayTradingGame(context=test_context, view=view)

    game.handle_import()

    assert "Import failed" in game.notice


def test_handle_quit(test_context):
    game = DayTradingGame(context=test_context)
    assert game.running is True

    game.handle_quit()

    assert game.running is False
    assert "Goodbye" in game.notice


def test_game_run_loop(test_context):
    view = MockTradingView(["p", "q"])
    game = DayTradingGame(context=test_context, view=view)

    game.run()

    assert game.running is False
    assert len(view.displayed_screens) >= 2


def test_play_day_trading_entrypoint(test_context):
    view = MockTradingView(["q"])
    play_day_trading(context=test_context, view=view)
    assert len(view.displayed_screens) == 1


def test_casino_games_and_main_registration():
    from casino import games
    from casino.games import day_trading
    from casino.main import GAME_HANDLERS

    assert hasattr(games, "day_trading")
    assert callable(day_trading.play_day_trading)
    assert "day trading" in GAME_HANDLERS
    assert GAME_HANDLERS["day trading"] == day_trading.play_day_trading
