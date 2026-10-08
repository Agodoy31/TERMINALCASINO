from typing import Optional
from casino.types import GameContext
from casino.accounts import Account
from casino.games.day_trading.models import Portfolio
from casino.games.day_trading.market import Market
from casino.games.day_trading.views import DayTradingView


class DayTradingGame:
    def __init__(
        self,
        context: GameContext,
        portfolio: Optional[Portfolio] = None,
        market: Optional[Market] = None,
        view: Optional[DayTradingView] = None,
        save_path: Optional[str] = None,
    ) -> None:
        self.context: GameContext = context
        self.account: Account = context.account
        self.market: Market = market if market is not None else Market()
        self.portfolio: Portfolio = portfolio if portfolio is not None else Portfolio()
        self.view: DayTradingView = view if view is not None else DayTradingView()
        self.current_page: int = 1
        self.notice: str = ""
        self.running: bool = True
        self.save_path: str = save_path if save_path is not None else "portfolio.json"

    def handle_command(self, cmd: str) -> None:
        clean_cmd = (cmd or "").strip().upper()
        if clean_cmd == "B":
            self.handle_buy()
        elif clean_cmd == "S":
            self.handle_sell()
        elif clean_cmd == "N":
            self.handle_next_tick()
        elif clean_cmd == "P":
            self.handle_page()
        elif clean_cmd == "D":
            self.handle_deposit()
        elif clean_cmd == "W":
            self.handle_withdraw()
        elif clean_cmd == "E":
            self.handle_export()
        elif clean_cmd == "I":
            self.handle_import()
        elif clean_cmd == "Q":
            self.handle_quit()
        else:
            self.notice = f"Invalid command: '{cmd}'. Available commands: B, S, N, P, D, W, E, I, Q."

    def handle_buy(self) -> None:
        ticker = self.view.prompt("Enter ticker symbol to buy: ").strip().upper()
        if not ticker:
            return

        price = self.market.get_price(ticker)
        if price is None:
            self.notice = f"Unknown ticker symbol: {ticker}."
            return

        shares_str = self.view.prompt(f"Enter number of shares of {ticker} to buy: ").strip()
        try:
            shares = int(shares_str)
            if shares <= 0:
                self.notice = "Shares must be a positive integer."
                return
        except ValueError:
            self.notice = "Invalid shares count. Must be a positive integer."
            return

        total_cost = round(shares * price, 2)
        if total_cost > self.portfolio.cash:
            self.notice = f"Insufficient funds: purchase of {shares} shares requires ${total_cost:.2f}, but portfolio cash is ${self.portfolio.cash:.2f}."
            return

        success = self.portfolio.buy(ticker, shares, price)
        if success:
            self.notice = f"Bought {shares} shares of {ticker} at ${price:.2f} for a total of ${total_cost:.2f}."
        else:
            self.notice = "Transaction failed."

    def handle_sell(self) -> None:
        ticker = self.view.prompt("Enter ticker symbol to sell: ").strip().upper()
        if not ticker:
            return

        owned = self.portfolio.holdings.get(ticker, 0)
        if owned <= 0:
            self.notice = f"No shares of {ticker} owned in portfolio."
            return

        shares_str = self.view.prompt(f"Enter number of shares of {ticker} to sell: ").strip()
        try:
            shares = int(shares_str)
            if shares <= 0:
                self.notice = "Shares must be a positive integer."
                return
            if shares > owned:
                self.notice = f"Cannot sell {shares} shares; only {owned} shares owned."
                return
        except ValueError:
            self.notice = "Invalid shares count. Must be a positive integer."
            return

        price = self.market.get_price(ticker)
        if price is None:
            self.notice = f"Unable to fetch market price for {ticker}."
            return

        proceeds = round(shares * price, 2)
        success = self.portfolio.sell(ticker, shares, price)
        if success:
            self.notice = f"Sold {shares} shares of {ticker} at ${price:.2f} for proceeds of ${proceeds:.2f}."
        else:
            self.notice = "Transaction failed."

    def handle_next_tick(self) -> None:
        self.market.advance_tick()
        if self.market.last_news:
            self.notice = f"Advanced to tick {self.market.tick_count}. News: {self.market.last_news}"
        else:
            self.notice = f"Advanced to tick {self.market.tick_count}."

    def handle_page(self) -> None:
        total_pages = DayTradingView.get_total_pages(len(self.market.get_quotes()), DayTradingView.ITEMS_PER_PAGE)
        self.current_page += 1
        if self.current_page > total_pages:
            self.current_page = 1
        self.notice = f"Page {self.current_page} of {total_pages}."

    def handle_deposit(self) -> None:
        amount_str = self.view.prompt("Enter chip amount to deposit into portfolio: ").strip()
        try:
            amount = int(amount_str)
            if amount <= 0:
                self.notice = "Deposit amount must be a positive integer."
                return
        except ValueError:
            self.notice = "Invalid deposit amount. Must be a positive integer."
            return

        if amount > self.account.balance:
            self.notice = f"Insufficient account balance: deposit amount {amount} exceeds {self.account.balance} chips."
            return

        try:
            self.portfolio.deposit_from_account(self.account, amount)
            self.notice = f"Deposited {amount} chips into portfolio cash."
        except ValueError as err:
            self.notice = f"Deposit failed: {err}"

    def handle_withdraw(self) -> None:
        amount_str = self.view.prompt("Enter chip amount to withdraw from portfolio: ").strip()
        try:
            amount = int(amount_str)
            if amount <= 0:
                self.notice = "Withdrawal amount must be a positive integer."
                return
        except ValueError:
            self.notice = "Invalid withdrawal amount. Must be a positive integer."
            return

        if amount > self.portfolio.cash:
            self.notice = f"Insufficient portfolio cash: withdrawal amount {amount} exceeds ${self.portfolio.cash:.2f}."
            return

        try:
            self.portfolio.withdraw_to_account(self.account, amount)
            self.notice = f"Withdrew {amount} chips to casino account."
        except ValueError as err:
            self.notice = f"Withdrawal failed: {err}"

    def handle_export(self) -> None:
        path_input = self.view.prompt(f"Enter file path to export [default: {self.save_path}]: ").strip()
        target_path = path_input if path_input else self.save_path
        try:
            self.portfolio.save_json(target_path)
            self.notice = f"Exported portfolio to {target_path}."
        except Exception as err:
            self.notice = f"Export failed: {err}"

    def handle_import(self) -> None:
        path_input = self.view.prompt(f"Enter file path to import [default: {self.save_path}]: ").strip()
        target_path = path_input if path_input else self.save_path
        try:
            self.portfolio = Portfolio.load_json(target_path)
            self.notice = f"Imported portfolio from {target_path}."
        except Exception as err:
            self.notice = f"Import failed: {err}"

    def handle_quit(self) -> None:
        self.running = False
        self.notice = "Exiting Day Trading Simulator. Goodbye!"

    def run(self) -> None:
        while self.running:
            self.view.display_screen(
                portfolio=self.portfolio,
                market=self.market,
                page=self.current_page,
                notice=self.notice,
                account=self.account,
            )
            cmd = self.view.prompt()
            self.handle_command(cmd)


def play_day_trading(
    context: GameContext,
    portfolio: Optional[Portfolio] = None,
    market: Optional[Market] = None,
    view: Optional[DayTradingView] = None,
) -> None:
    game = DayTradingGame(
        context=context,
        portfolio=portfolio,
        market=market,
        view=view,
    )
    game.run()
