import pytest
from casino.games.day_trading.equities import DEFAULT_EQUITIES
from casino.games.day_trading.market import Market, MarketEvent, Stock


def test_equities_universe_size():
    assert 50 <= len(DEFAULT_EQUITIES) <= 70


def test_equities_universe_structure():
    symbols = set()
    for entry in DEFAULT_EQUITIES:
        symbol = entry["symbol"]
        assert symbol.isupper()
        assert symbol not in symbols
        symbols.add(symbol)

        assert isinstance(entry["name"], str)
        assert len(entry["name"]) > 0

        assert isinstance(entry["price"], (int, float))
        assert entry["price"] > 0

        assert isinstance(entry["volatility"], float)
        assert 0.015 <= entry["volatility"] <= 0.06

        assert isinstance(entry["sector"], str)
        assert len(entry["sector"]) > 0


def test_stock_dataclass_properties():
    stock = Stock(
        symbol="AAPL",
        name="Apple Inc.",
        price=150.00,
        previous_price=140.00,
        volatility=0.02,
        trend=0.0,
        sector="Technology",
    )
    assert stock.price_change == 10.00
    assert stock.percent_change == 7.14

    stock_down = Stock(
        symbol="MSFT",
        name="Microsoft Corporation",
        price=95.00,
        previous_price=100.00,
        volatility=0.02,
    )
    assert stock_down.price_change == -5.00
    assert stock_down.percent_change == -5.00

    stock_zero_prev = Stock(
        symbol="NEW",
        name="New Asset",
        price=10.00,
        previous_price=0.0,
        volatility=0.02,
    )
    assert stock_zero_prev.percent_change == 0.0


def test_market_event_dataclass():
    event = MarketEvent(
        headline="Apple beats earnings expectations",
        target_symbol="AAPL",
        multiplier=1.10,
    )
    assert event.headline == "Apple beats earnings expectations"
    assert event.target_symbol == "AAPL"
    assert event.multiplier == 1.10


def test_market_initialization():
    market = Market(seed=42)
    assert market.tick_count == 1
    assert market.last_news is None
    assert len(market.stocks) == len(DEFAULT_EQUITIES)
    assert "AAPL" in market.stocks

    aapl = market.stocks["AAPL"]
    assert aapl.price > 0
    assert aapl.previous_price == aapl.price
    assert aapl.price_change == 0.0
    assert aapl.percent_change == 0.0


def test_deterministic_advance_tick():
    market1 = Market(seed=12345)
    market2 = Market(seed=12345)

    prices1 = market1.advance_tick()
    prices2 = market2.advance_tick()

    assert market1.tick_count == 2
    assert market2.tick_count == 2
    assert prices1 == prices2

    prices1_tick3 = market1.advance_tick()
    prices2_tick3 = market2.advance_tick()
    assert market1.tick_count == 3
    assert market2.tick_count == 3
    assert prices1_tick3 == prices2_tick3


def test_divergent_seeds():
    market1 = Market(seed=111)
    market2 = Market(seed=999)

    prices1 = market1.advance_tick()
    prices2 = market2.advance_tick()

    assert prices1 != prices2


def test_price_floor_enforcement():
    market = Market(seed=42)
    test_stock = market.stocks["AAPL"]
    test_stock.price = 1.05
    test_stock.volatility = 0.50
    test_stock.trend = -0.90

    for _ in range(10):
        market.advance_tick()
        assert market.stocks["AAPL"].price >= 1.00


def test_severe_down_multiplier_price_floor():
    market = Market(seed=42)
    collapse_event = MarketEvent(
        headline="Catastrophic breakdown triggers emergency halt",
        target_symbol="AAPL",
        multiplier=0.01,
    )
    market.advance_tick(forced_event=collapse_event)
    assert market.stocks["AAPL"].price >= 1.00


def test_news_event_firing_and_multiplier_effect():
    market = Market(seed=42)
    initial_aapl_price = market.stocks["AAPL"].price
    market.stocks["AAPL"].volatility = 0.0
    market.stocks["AAPL"].trend = 0.0

    beat_event = MarketEvent(
        headline="Apple crushes quarterly earnings",
        target_symbol="AAPL",
        multiplier=1.15,
    )
    market.advance_tick(forced_event=beat_event)

    expected_price = max(1.00, round(initial_aapl_price * 1.15, 2))
    assert market.stocks["AAPL"].price == expected_price
    assert market.last_news == "Apple crushes quarterly earnings"


def test_news_clearing_on_untriggered_tick():
    market = Market(seed=42)
    beat_event = MarketEvent(
        headline="Apple crushes quarterly earnings",
        target_symbol="AAPL",
        multiplier=1.15,
    )
    market.advance_tick(forced_event=beat_event)
    assert market.last_news is not None

    while market.last_news is not None:
        market.advance_tick()

    assert market.last_news is None


def test_forced_event_roll():
    market = Market(seed=42)
    market.advance_tick(force_event=True)
    assert market.last_news is not None
    assert isinstance(market.last_news, str)


def test_get_price_valid_and_case_insensitive():
    market = Market(seed=42)
    price_upper = market.get_price("AAPL")
    price_lower = market.get_price("aapl")
    price_mixed = market.get_price("AaPl")

    assert price_upper is not None
    assert price_upper == price_lower == price_mixed
    assert price_upper == market.stocks["AAPL"].price


def test_get_price_invalid_symbol():
    market = Market(seed=42)
    assert market.get_price("NONEXISTENT") is None
    assert market.get_price("") is None


def test_get_quotes_returns_isolated_dict_copy():
    market = Market(seed=42)
    quotes = market.get_quotes()

    assert len(quotes) == len(market.stocks)
    assert "AAPL" in quotes

    quotes.pop("AAPL")
    assert "AAPL" in market.stocks
