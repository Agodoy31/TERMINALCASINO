from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from casino.accounts import Account


@dataclass
class TradeRecord:
    trade_type: str
    symbol: str
    shares: int
    price: float
    total_amount: float
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "trade_type": self.trade_type,
            "symbol": self.symbol,
            "shares": self.shares,
            "price": round(self.price, 2),
            "total_amount": round(self.total_amount, 2),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TradeRecord":
        return cls(
            trade_type=str(data["trade_type"]).upper(),
            symbol=str(data["symbol"]).upper(),
            shares=int(data["shares"]),
            price=round(float(data["price"]), 2),
            total_amount=round(float(data["total_amount"]), 2),
            timestamp=str(data["timestamp"]),
        )


@dataclass
class Portfolio:
    cash: float = 1000.0
    holdings: dict[str, int] = field(default_factory=dict)
    history: list[TradeRecord] = field(default_factory=list)

    def buy(
        self,
        symbol: str,
        shares: int,
        price: float,
        timestamp: str | None = None,
    ) -> bool:
        if shares <= 0:
            raise ValueError("Shares must be positive")
        if price <= 0:
            raise ValueError("Price must be positive")

        cost = round(shares * price, 2)
        if self.cash < cost:
            return False

        self.cash = round(self.cash - cost, 2)
        normalized_symbol = symbol.upper()
        self.holdings[normalized_symbol] = (
            self.holdings.get(normalized_symbol, 0) + shares
        )

        ts = timestamp or datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        record = TradeRecord(
            trade_type="BUY",
            symbol=normalized_symbol,
            shares=shares,
            price=round(price, 2),
            total_amount=cost,
            timestamp=ts,
        )
        self.history.append(record)
        return True

    def sell(
        self,
        symbol: str,
        shares: int,
        price: float,
        timestamp: str | None = None,
    ) -> bool:
        if shares <= 0:
            raise ValueError("Shares must be positive")
        if price <= 0:
            raise ValueError("Price must be positive")

        normalized_symbol = symbol.upper()
        owned = self.holdings.get(normalized_symbol, 0)
        if owned < shares:
            return False

        proceeds = round(shares * price, 2)
        self.cash = round(self.cash + proceeds, 2)
        self.holdings[normalized_symbol] -= shares
        if self.holdings[normalized_symbol] == 0:
            del self.holdings[normalized_symbol]

        ts = timestamp or datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        record = TradeRecord(
            trade_type="SELL",
            symbol=normalized_symbol,
            shares=shares,
            price=round(price, 2),
            total_amount=proceeds,
            timestamp=ts,
        )
        self.history.append(record)
        return True

    def total_value(self, current_prices: dict) -> float:
        stock_equity = 0.0
        for sym, shares in self.holdings.items():
            current_price = current_prices.get(sym, current_prices.get(sym.upper(), 0.0))
            stock_equity += shares * float(current_price)
        return round(self.cash + stock_equity, 2)

    def deposit_from_account(self, account: Account, amount: int) -> None:
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        account.withdraw(amount)
        self.cash = round(self.cash + amount, 2)

    def withdraw_to_account(self, account: Account, amount: int) -> None:
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        if self.cash < amount:
            raise ValueError("Insufficient cash in trading portfolio")
        self.cash = round(self.cash - amount, 2)
        account.deposit(amount)

    def to_dict(self) -> dict:
        return {
            "cash": round(self.cash, 2),
            "holdings": dict(self.holdings),
            "history": [record.to_dict() for record in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Portfolio":
        cash = float(data.get("cash", 1000.0))
        raw_holdings = data.get("holdings", {})
        holdings = {
            str(k).upper(): int(v)
            for k, v in raw_holdings.items()
            if int(v) > 0
        }
        raw_history = data.get("history", [])
        history = [TradeRecord.from_dict(item) for item in raw_history]
        return cls(
            cash=round(cash, 2),
            holdings=holdings,
            history=history,
        )

    def save_json(self, file_path: str) -> None:
        path = Path(file_path)
        if path.parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_json(cls, file_path: str) -> "Portfolio":
        path = Path(file_path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
