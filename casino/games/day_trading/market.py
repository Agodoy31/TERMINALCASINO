from dataclasses import dataclass
from typing import Optional
import random
from casino.games.day_trading.equities import DEFAULT_EQUITIES


@dataclass
class Stock:
    symbol: str
    name: str
    price: float
    previous_price: float
    volatility: float
    trend: float = 0.0
    sector: str = ""

    @property
    def price_change(self) -> float:
        return round(self.price - self.previous_price, 2)

    @property
    def percent_change(self) -> float:
        if self.previous_price == 0.0:
            return 0.0
        delta = self.price - self.previous_price
        return round((delta / self.previous_price) * 100.0, 2)


@dataclass
class MarketEvent:
    headline: str
    target_symbol: Optional[str]
    multiplier: float


class Market:
    EVENT_TEMPLATES = [
        {
            "type": "earnings_beat",
            "headline_template": "{name} smashes quarterly earnings expectations with record revenue",
            "multiplier_range": (1.06, 1.15),
        },
        {
            "type": "clinical_trial_win",
            "headline_template": "{name} announces successful phase 3 clinical trial results",
            "multiplier_range": (1.08, 1.18),
        },
        {
            "type": "supply_bottleneck",
            "headline_template": "{name} warns of severe factory delays and supply chain bottlenecks",
            "multiplier_range": (0.85, 0.94),
        },
        {
            "type": "regulatory_investigation",
            "headline_template": "Antitrust regulators launch formal inquiry into business practices of {name}",
            "multiplier_range": (0.82, 0.92),
        },
        {
            "type": "rate_cut",
            "headline_template": "Federal Reserve cuts interest rates unexpectedly sparking market rally",
            "multiplier_range": (1.02, 1.06),
        },
    ]

    def __init__(self, seed: Optional[int] = None) -> None:
        self.rng = random.Random(seed)
        self.tick_count: int = 1
        self.last_news: Optional[str] = None
        self.stocks: dict[str, Stock] = {}

        for entry in DEFAULT_EQUITIES:
            ticker = str(entry["symbol"]).upper()
            base_price = round(float(entry["price"]), 2)
            self.stocks[ticker] = Stock(
                symbol=ticker,
                name=str(entry["name"]),
                price=base_price,
                previous_price=base_price,
                volatility=float(entry["volatility"]),
                trend=float(entry.get("trend", 0.0)),
                sector=str(entry.get("sector", "")),
            )

    def _generate_event(self) -> MarketEvent:
        template = self.rng.choice(self.EVENT_TEMPLATES)
        event_type = template["type"]
        low_mult, high_mult = template["multiplier_range"]
        mult = round(self.rng.uniform(low_mult, high_mult), 4)

        if event_type == "clinical_trial_win":
            candidates = [s for s in self.stocks.values() if s.sector == "Healthcare"]
            target = self.rng.choice(candidates) if candidates else self.rng.choice(list(self.stocks.values()))
            headline = template["headline_template"].format(name=target.name, symbol=target.symbol)
            return MarketEvent(headline=headline, target_symbol=target.symbol, multiplier=mult)

        if event_type == "rate_cut":
            headline = template["headline_template"]
            return MarketEvent(headline=headline, target_symbol=None, multiplier=mult)

        target = self.rng.choice(list(self.stocks.values()))
        headline = template["headline_template"].format(name=target.name, symbol=target.symbol)
        return MarketEvent(headline=headline, target_symbol=target.symbol, multiplier=mult)

    def advance_tick(
        self,
        forced_event: Optional[MarketEvent] = None,
        force_event: bool = False,
    ) -> dict[str, float]:
        self.tick_count += 1

        for stock in self.stocks.values():
            stock.previous_price = stock.price

        event_to_apply = forced_event
        if event_to_apply is None and force_event:
            event_to_apply = self._generate_event()
        elif event_to_apply is None:
            if self.rng.random() < 0.20:
                event_to_apply = self._generate_event()

        if event_to_apply is not None:
            self.last_news = event_to_apply.headline
            if event_to_apply.target_symbol is not None:
                target = self.stocks.get(event_to_apply.target_symbol.upper())
                if target is not None:
                    target.price = max(1.00, round(target.price * event_to_apply.multiplier, 2))
            else:
                for stock in self.stocks.values():
                    stock.price = max(1.00, round(stock.price * event_to_apply.multiplier, 2))
        else:
            self.last_news = None

        for stock in self.stocks.values():
            shock = self.rng.gauss(0.0, stock.volatility)
            new_price = stock.price * (1.0 + stock.trend + shock)
            stock.price = max(1.00, round(new_price, 2))

        return {stock.symbol: stock.price for stock in self.stocks.values()}

    def get_price(self, symbol: str) -> Optional[float]:
        if not symbol:
            return None
        stock = self.stocks.get(symbol.strip().upper())
        if stock is None:
            return None
        return stock.price

    def get_quotes(self) -> dict[str, Stock]:
        return dict(self.stocks)
