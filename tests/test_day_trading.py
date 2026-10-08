"""End to end integration test suite for the Day Trading simulator.

Validates session lifecycle, game loop dispatch, economic invariants,
and persistence error handling.
"""

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import json
import pytest

from casino.accounts import Account
from casino.config import Config
from casino.types import GameContext
from casino.games.day_trading.models import Portfolio, TradeRecord
from casino.games.day_trading.market import Market
from casino.games.day_trading.views import DayTradingView
from casino.games.day_trading.game import DayTradingGame, play_day_trading
from casino.main import GAME_HANDLERS


class MockInteractiveView:
    """Mock view recording display calls and supplying scripted inputs."""

    def __init__(self, inputs=None):
        self.inputs = list(inputs or [])
        self.displayed_screens = []

    def prompt(self, prompt_text=""):
        if self.inputs:
            return self.inputs.pop(0)
        return ""

    def display_screen(self, portfolio, market, page, notice, account):
        self.displayed_screens.append({
            "portfolio": portfolio,
            "market": market,
            "page": page,
            "notice": notice,
            "account": account,
        })


def test_full_day_trading_session_lifecycle(tmp_path):
    """Verify complete end to end day trading lifecycle across all subsystems."""
    account = Account(aid=uuid4(), name="SessionTester", balance=500)
    market = Market(seed=42)
    portfolio = Portfolio(cash=1000.0)

    # Deposit 200 chips from casino Account into Portfolio cash
    initial_cash = portfolio.cash
    portfolio.deposit_from_account(account, 200)
    assert account.balance == 300
    assert portfolio.cash == round(initial_cash + 200.0, 2)

    # Buy shares of prominent equities like AAPL and MSFT from the market
    aapl_price = market.get_price("AAPL")
    msft_price = market.get_price("MSFT")
    assert aapl_price is not None
    assert msft_price is not None

    assert portfolio.buy("AAPL", 3, aapl_price) is True
    assert portfolio.buy("MSFT", 1, msft_price) is True
    assert portfolio.holdings["AAPL"] == 3
    assert portfolio.holdings["MSFT"] == 1
    assert len(portfolio.history) == 2

    # Advance ticks across multiple cycles, checking that tick count increments and stock prices evolve
    initial_tick = market.tick_count
    for _ in range(5):
        market.advance_tick()
    assert market.tick_count == initial_tick + 5

    new_aapl_price = market.get_price("AAPL")
    new_msft_price = market.get_price("MSFT")
    assert new_aapl_price is not None
    assert new_msft_price is not None

    # Sell a portion of AAPL shares, asserting cash balance increases and trade record history is appended
    cash_before_partial_sell = portfolio.cash
    history_count_before = len(portfolio.history)
    assert portfolio.sell("AAPL", 1, new_aapl_price) is True
    assert portfolio.holdings["AAPL"] == 2
    assert portfolio.cash > cash_before_partial_sell
    assert len(portfolio.history) == history_count_before + 1
    assert portfolio.history[-1].trade_type == "SELL"
    assert portfolio.history[-1].symbol == "AAPL"
    assert portfolio.history[-1].shares == 1

    # Sell all MSFT shares, asserting position is completely liquidated and MSFT key is pruned from holdings dictionary
    assert portfolio.sell("MSFT", 1, new_msft_price) is True
    assert "MSFT" not in portfolio.holdings

    # Withdraw 150 chips from trading cash to casino Account, asserting casino balance becomes 450
    cash_before_withdrawal = portfolio.cash
    portfolio.withdraw_to_account(account, 150)
    assert account.balance == 450
    assert portfolio.cash == round(cash_before_withdrawal - 150.0, 2)

    # Export portfolio to a temporary JSON file via save_json
    save_file = str(tmp_path / "lifecycle_portfolio.json")
    portfolio.save_json(save_file)
    assert Path(save_file).is_file()

    # Load portfolio from the temporary JSON file via load_json into a new instance
    loaded_portfolio = Portfolio.load_json(save_file)
    assert loaded_portfolio.cash == portfolio.cash
    assert loaded_portfolio.holdings == portfolio.holdings
    assert len(loaded_portfolio.history) == len(portfolio.history)
    for orig, loaded in zip(portfolio.history, loaded_portfolio.history):
        assert orig.to_dict() == loaded.to_dict()


def test_game_loop_interactive_mock_session(tmp_path):
    """Verify interactive game loop execution across all command dispatches."""
    account = Account(aid=uuid4(), name="Alice", balance=800)
    context = GameContext(account=account, config=Config.default())
    portfolio = Portfolio(cash=600.0)
    market = Market(seed=123)
    export_path = str(tmp_path / "interactive_export.json")

    mock_inputs = [
        "D", "100",
        "B", "AAPL", "2",
        "N",
        "P",
        "S", "AAPL", "1",
        "W", "50",
        "E", export_path,
        "I", export_path,
        "Q",
    ]

    view = MockInteractiveView(mock_inputs)
    game = DayTradingGame(
        context=context,
        portfolio=portfolio,
        market=market,
        view=view,
    )
    game.run()

    assert game.running is False
    assert account.balance == 750
    assert game.market.tick_count == 2
    assert game.current_page == 2
    assert game.portfolio.holdings == {"AAPL": 1}
    assert Path(export_path).is_file()
    assert len(view.displayed_screens) == 9
    assert "Exiting Day Trading Simulator" in game.notice


def test_main_casino_game_handlers_dispatch():
    """Verify registration and execution via casino main game handlers mapping."""
    import casino.games.day_trading as dt_module

    assert "day trading" in GAME_HANDLERS
    assert GAME_HANDLERS["day trading"] is dt_module.play_day_trading

    account = Account(aid=uuid4(), name="CasinoTester", balance=500)
    context = GameContext(account=account, config=Config.default())

    # Mock view to cleanly exit on first prompt
    mock_view = MockInteractiveView(["Q"])
    dt_module.play_day_trading(context=context, view=mock_view)
    assert len(mock_view.displayed_screens) == 1

    # Also test dispatch without custom view by patching DayTradingView methods
    with patch.object(DayTradingView, "display_screen") as mock_screen, \
         patch.object(DayTradingView, "prompt", return_value="Q") as mock_prompt:
        GAME_HANDLERS["day trading"](context)
        assert mock_screen.call_count == 1
        assert mock_prompt.call_count == 1


def test_balance_integrity_and_economic_invariants():
    """Verify balance preservation and transaction failure invariants."""
    account = Account(aid=uuid4(), name="InvariantTester", balance=1000)
    portfolio = Portfolio(cash=500.0)
    initial_total_capital = round(account.balance + portfolio.cash, 2)

    # Deposit transfer preserves total capital
    portfolio.deposit_from_account(account, 300)
    assert round(account.balance + portfolio.cash, 2) == initial_total_capital
    assert account.balance == 700
    assert portfolio.cash == 800.0

    # Withdrawal transfer preserves total capital
    portfolio.withdraw_to_account(account, 250)
    assert round(account.balance + portfolio.cash, 2) == initial_total_capital
    assert account.balance == 950
    assert portfolio.cash == 550.0

    # Cyclical deposits and withdrawals maintain invariant
    for transfer_amt in [100, 200, 50, 75]:
        portfolio.deposit_from_account(account, transfer_amt)
        assert round(account.balance + portfolio.cash, 2) == initial_total_capital
        portfolio.withdraw_to_account(account, transfer_amt)
        assert round(account.balance + portfolio.cash, 2) == initial_total_capital

    current_account_balance = account.balance
    current_portfolio_cash = portfolio.cash
    current_holdings = dict(portfolio.holdings)
    current_history_len = len(portfolio.history)

    # Overdraft deposit does not mutate balances
    with pytest.raises(ValueError):
        portfolio.deposit_from_account(account, account.balance + 100)
    assert account.balance == current_account_balance
    assert portfolio.cash == current_portfolio_cash

    with pytest.raises(ValueError):
        portfolio.deposit_from_account(account, -50)
    assert account.balance == current_account_balance
    assert portfolio.cash == current_portfolio_cash

    # Overdraft withdrawal does not mutate balances
    with pytest.raises(ValueError):
        portfolio.withdraw_to_account(account, int(portfolio.cash) + 500)
    assert account.balance == current_account_balance
    assert portfolio.cash == current_portfolio_cash

    with pytest.raises(ValueError):
        portfolio.withdraw_to_account(account, 0)
    assert account.balance == current_account_balance
    assert portfolio.cash == current_portfolio_cash

    # Failed buy due to insufficient funds preserves cash holdings and history
    buy_result = portfolio.buy("AAPL", 100000, 200.0)
    assert buy_result is False
    assert portfolio.cash == current_portfolio_cash
    assert portfolio.holdings == current_holdings
    assert len(portfolio.history) == current_history_len

    # Failed buy due to invalid negative values preserves state
    with pytest.raises(ValueError):
        portfolio.buy("AAPL", -5, 100.0)
    with pytest.raises(ValueError):
        portfolio.buy("AAPL", 5, -100.0)
    assert portfolio.cash == current_portfolio_cash
    assert portfolio.holdings == current_holdings
    assert len(portfolio.history) == current_history_len

    # Failed sell due to unowned ticker preserves state
    sell_result = portfolio.sell("NVDA", 10, 100.0)
    assert sell_result is False
    assert portfolio.cash == current_portfolio_cash
    assert portfolio.holdings == current_holdings
    assert len(portfolio.history) == current_history_len

    # Buy 2 shares then fail to sell 5 shares
    assert portfolio.buy("NVDA", 2, 100.0) is True
    post_buy_cash = portfolio.cash
    post_buy_holdings = dict(portfolio.holdings)
    post_buy_history_len = len(portfolio.history)

    excess_sell_result = portfolio.sell("NVDA", 5, 100.0)
    assert excess_sell_result is False
    assert portfolio.cash == post_buy_cash
    assert portfolio.holdings == post_buy_holdings
    assert len(portfolio.history) == post_buy_history_len

    with pytest.raises(ValueError):
        portfolio.sell("NVDA", -1, 100.0)
    with pytest.raises(ValueError):
        portfolio.sell("NVDA", 1, -50.0)
    assert portfolio.cash == post_buy_cash
    assert portfolio.holdings == post_buy_holdings
    assert len(portfolio.history) == post_buy_history_len


def test_file_persistence_error_recovery(tmp_path):
    """Verify game loop error recovery when encountering invalid persistence files."""
    account = Account(aid=uuid4(), name="PersistenceTester", balance=500)
    context = GameContext(account=account, config=Config.default())
    original_holdings = {"AAPL": 5, "MSFT": 2}
    portfolio = Portfolio(cash=450.0, holdings=dict(original_holdings))

    # 1. Nonexistent file import
    missing_path = str(tmp_path / "nonexistent_portfolio.json")
    view_missing = MockInteractiveView(["I", missing_path, "Q"])
    game_missing = DayTradingGame(
        context=context,
        portfolio=portfolio,
        view=view_missing,
    )
    game_missing.run()

    assert game_missing.running is False
    assert any("Import failed" in screen["notice"] for screen in view_missing.displayed_screens)
    assert game_missing.portfolio.cash == 450.0
    assert game_missing.portfolio.holdings == original_holdings

    # 2. Corrupted JSON file import
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("{malformed: json, syntax", encoding="utf-8")
    view_corrupt = MockInteractiveView(["I", str(corrupt_file), "Q"])
    game_corrupt = DayTradingGame(
        context=context,
        portfolio=portfolio,
        view=view_corrupt,
    )
    game_corrupt.run()

    assert game_corrupt.running is False
    assert any("Import failed" in screen["notice"] for screen in view_corrupt.displayed_screens)
    assert game_corrupt.portfolio.cash == 450.0
    assert game_corrupt.portfolio.holdings == original_holdings

    # 3. Invalid schema data import
    invalid_schema_file = tmp_path / "invalid_schema.json"
    invalid_schema_file.write_text(
        json.dumps({"cash": "not_numeric", "holdings": "not_dict"}),
        encoding="utf-8",
    )
    view_invalid_schema = MockInteractiveView(["I", str(invalid_schema_file), "Q"])
    game_invalid_schema = DayTradingGame(
        context=context,
        portfolio=portfolio,
        view=view_invalid_schema,
    )
    game_invalid_schema.run()

    assert game_invalid_schema.running is False
    assert any("Import failed" in screen["notice"] for screen in view_invalid_schema.displayed_screens)
    assert game_invalid_schema.portfolio.cash == 450.0
    assert game_invalid_schema.portfolio.holdings == original_holdings

    # 4. Direct command execution error notice validation
    view_direct = MockInteractiveView([missing_path])
    game_direct = DayTradingGame(
        context=context,
        portfolio=portfolio,
        view=view_direct,
    )
    game_direct.handle_command("I")
    assert "Import failed" in game_direct.notice
    assert game_direct.portfolio.cash == 450.0
    assert game_direct.portfolio.holdings == original_holdings

    # 5. Export error recovery
    with patch.object(portfolio, "save_json", side_effect=OSError("Disk write error")):
        view_export_err = MockInteractiveView(["E", "test.json", "Q"])
        game_export_err = DayTradingGame(
            context=context,
            portfolio=portfolio,
            view=view_export_err,
        )
        game_export_err.run()

        assert game_export_err.running is False
        assert any("Export failed" in screen["notice"] for screen in view_export_err.displayed_screens)
        assert game_export_err.portfolio.cash == 450.0
        assert game_export_err.portfolio.holdings == original_holdings
