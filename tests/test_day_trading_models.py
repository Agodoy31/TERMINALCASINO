import json
from pathlib import Path
import pytest
from casino.accounts import Account
from casino.games.day_trading.models import Portfolio, TradeRecord


def test_trade_record_creation_and_dict_serialization():
    record = TradeRecord(
        trade_type="BUY",
        symbol="AAPL",
        shares=10,
        price=150.25,
        total_amount=1502.50,
        timestamp="2026-10-08 12:00:00 UTC",
    )
    assert record.trade_type == "BUY"
    assert record.symbol == "AAPL"
    assert record.shares == 10
    assert record.price == 150.25
    assert record.total_amount == 1502.50
    assert record.timestamp == "2026-10-08 12:00:00 UTC"

    data = record.to_dict()
    assert data["trade_type"] == "BUY"
    assert data["symbol"] == "AAPL"
    assert data["shares"] == 10
    assert data["price"] == 150.25
    assert data["total_amount"] == 1502.50
    assert data["timestamp"] == "2026-10-08 12:00:00 UTC"

    restored = TradeRecord.from_dict(data)
    assert restored.trade_type == record.trade_type
    assert restored.symbol == record.symbol
    assert restored.shares == record.shares
    assert restored.price == record.price
    assert restored.total_amount == record.total_amount
    assert restored.timestamp == record.timestamp


def test_portfolio_default_initialization():
    portfolio = Portfolio()
    assert portfolio.cash == 1000.0
    assert portfolio.holdings == {}
    assert portfolio.history == []


def test_portfolio_custom_initialization():
    record = TradeRecord("BUY", "MSFT", 5, 300.0, 1500.0, "2026-10-08 12:00:00 UTC")
    portfolio = Portfolio(cash=2500.50, holdings={"MSFT": 5}, history=[record])
    assert portfolio.cash == 2500.50
    assert portfolio.holdings == {"MSFT": 5}
    assert len(portfolio.history) == 1
    assert portfolio.history[0].symbol == "MSFT"


def test_portfolio_buy_success():
    portfolio = Portfolio(cash=1000.0)
    result = portfolio.buy("NVDA", 4, 150.0)
    assert result is True
    assert portfolio.cash == 400.0
    assert portfolio.holdings == {"NVDA": 4}
    assert len(portfolio.history) == 1
    entry = portfolio.history[0]
    assert entry.trade_type == "BUY"
    assert entry.symbol == "NVDA"
    assert entry.shares == 4
    assert entry.price == 150.0
    assert entry.total_amount == 600.0
    assert isinstance(entry.timestamp, str)


def test_portfolio_buy_insufficient_cash():
    portfolio = Portfolio(cash=100.0)
    result = portfolio.buy("AMZN", 2, 80.0)
    assert result is False
    assert portfolio.cash == 100.0
    assert portfolio.holdings == {}
    assert len(portfolio.history) == 0


def test_portfolio_buy_invalid_inputs():
    portfolio = Portfolio(cash=1000.0)
    with pytest.raises(ValueError):
        portfolio.buy("AAPL", 0, 150.0)
    with pytest.raises(ValueError):
        portfolio.buy("AAPL", -5, 150.0)
    with pytest.raises(ValueError):
        portfolio.buy("AAPL", 5, 0.0)
    with pytest.raises(ValueError):
        portfolio.buy("AAPL", 5, -10.0)


def test_portfolio_buy_ticker_uppercased_and_accumulated():
    portfolio = Portfolio(cash=2000.0)
    portfolio.buy("goog", 2, 100.0)
    assert "GOOG" in portfolio.holdings
    assert portfolio.holdings["GOOG"] == 2
    portfolio.buy("GOOG", 3, 110.0)
    assert portfolio.holdings["GOOG"] == 5
    assert len(portfolio.history) == 2


def test_portfolio_sell_success_partial():
    portfolio = Portfolio(cash=500.0, holdings={"TSLA": 10})
    result = portfolio.sell("TSLA", 4, 200.0)
    assert result is True
    assert portfolio.cash == 1300.0
    assert portfolio.holdings == {"TSLA": 6}
    assert len(portfolio.history) == 1
    entry = portfolio.history[0]
    assert entry.trade_type == "SELL"
    assert entry.symbol == "TSLA"
    assert entry.shares == 4
    assert entry.price == 200.0
    assert entry.total_amount == 800.0


def test_portfolio_sell_success_pruning_zero_holdings():
    portfolio = Portfolio(cash=200.0, holdings={"META": 5})
    result = portfolio.sell("meta", 5, 300.0)
    assert result is True
    assert portfolio.cash == 1700.0
    assert "META" not in portfolio.holdings
    assert len(portfolio.holdings) == 0
    assert len(portfolio.history) == 1


def test_portfolio_sell_insufficient_shares():
    portfolio = Portfolio(cash=500.0, holdings={"JPM": 3})
    result = portfolio.sell("JPM", 4, 150.0)
    assert result is False
    assert portfolio.cash == 500.0
    assert portfolio.holdings == {"JPM": 3}
    assert len(portfolio.history) == 0

    unowned_result = portfolio.sell("XOM", 1, 100.0)
    assert unowned_result is False
    assert len(portfolio.history) == 0


def test_portfolio_sell_invalid_inputs():
    portfolio = Portfolio(cash=500.0, holdings={"AAPL": 10})
    with pytest.raises(ValueError):
        portfolio.sell("AAPL", 0, 150.0)
    with pytest.raises(ValueError):
        portfolio.sell("AAPL", -2, 150.0)
    with pytest.raises(ValueError):
        portfolio.sell("AAPL", 2, 0.0)
    with pytest.raises(ValueError):
        portfolio.sell("AAPL", 2, -50.0)


def test_portfolio_total_value_calculation():
    portfolio = Portfolio(cash=250.75, holdings={"AAPL": 10, "MSFT": 5})
    current_prices = {"AAPL": 150.50, "MSFT": 300.20, "GOOG": 120.00}
    expected_value = round(250.75 + 10 * 150.50 + 5 * 300.20, 2)
    assert portfolio.total_value(current_prices) == expected_value


def test_portfolio_total_value_missing_price_defaults_to_zero():
    portfolio = Portfolio(cash=500.0, holdings={"UNKNOWN": 10})
    current_prices = {"AAPL": 150.0}
    assert portfolio.total_value(current_prices) == 500.0


def test_portfolio_deposit_from_account_success():
    account = Account.generate("Alice", 500)
    portfolio = Portfolio(cash=1000.0)
    portfolio.deposit_from_account(account, 200)
    assert account.balance == 300
    assert portfolio.cash == 1200.0


def test_portfolio_deposit_from_account_invalid_amount():
    account = Account.generate("Alice", 500)
    portfolio = Portfolio(cash=1000.0)
    with pytest.raises(ValueError):
        portfolio.deposit_from_account(account, 0)
    with pytest.raises(ValueError):
        portfolio.deposit_from_account(account, -50)
    assert account.balance == 500
    assert portfolio.cash == 1000.0


def test_portfolio_deposit_from_account_insufficient_balance():
    account = Account.generate("Alice", 100)
    portfolio = Portfolio(cash=1000.0)
    with pytest.raises(ValueError):
        portfolio.deposit_from_account(account, 250)
    assert account.balance == 100
    assert portfolio.cash == 1000.0


def test_portfolio_withdraw_to_account_success():
    account = Account.generate("Bob", 100)
    portfolio = Portfolio(cash=800.0)
    portfolio.withdraw_to_account(account, 300)
    assert account.balance == 400
    assert portfolio.cash == 500.0


def test_portfolio_withdraw_to_account_invalid_amount():
    account = Account.generate("Bob", 100)
    portfolio = Portfolio(cash=800.0)
    with pytest.raises(ValueError):
        portfolio.withdraw_to_account(account, 0)
    with pytest.raises(ValueError):
        portfolio.withdraw_to_account(account, -100)
    assert account.balance == 100
    assert portfolio.cash == 800.0


def test_portfolio_withdraw_to_account_insufficient_cash():
    account = Account.generate("Bob", 100)
    portfolio = Portfolio(cash=250.0)
    with pytest.raises(ValueError):
        portfolio.withdraw_to_account(account, 500)
    assert account.balance == 100
    assert portfolio.cash == 250.0


def test_portfolio_to_dict_and_from_dict():
    original = Portfolio(cash=1234.56, holdings={"AAPL": 10, "TSLA": 4})
    original.buy("MSFT", 2, 200.0)
    data = original.to_dict()
    restored = Portfolio.from_dict(data)

    assert restored.cash == original.cash
    assert restored.holdings == original.holdings
    assert len(restored.history) == len(original.history)
    assert restored.history[0].symbol == original.history[0].symbol


def test_portfolio_save_and_load_json(tmp_path: Path):
    target_file = tmp_path / "nested" / "portfolio.json"
    portfolio = Portfolio(cash=3500.25, holdings={"NVDA": 8})
    portfolio.buy("AMZN", 5, 120.0)

    portfolio.save_json(str(target_file))
    assert target_file.exists()

    with open(target_file, "r", encoding="utf-8") as f:
        raw_content = json.load(f)
    assert raw_content["cash"] == portfolio.cash
    assert raw_content["holdings"] == portfolio.holdings

    loaded = Portfolio.load_json(str(target_file))
    assert loaded.cash == portfolio.cash
    assert loaded.holdings == portfolio.holdings
    assert len(loaded.history) == len(portfolio.history)
    assert loaded.history[0].symbol == "AMZN"
